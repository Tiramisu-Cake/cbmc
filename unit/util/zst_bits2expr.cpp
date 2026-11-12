// Author: Tiramisu-Cake <igkharin@gmail.com>
/// \file
/// Zero-width array reconstruction and preservation of nonzero siblings.

#include <util/arith_tools.h>
#include <util/bitvector_types.h>
#include <util/c_types.h>
#include <util/cmdline.h>
#include <util/config.h>
#include <util/namespace.h>
#include <util/simplify_utils.h>
#include <util/std_expr.h>
#include <util/std_types.h>
#include <util/symbol_table.h>

#include <testing-utils/empty_namespace.h>
#include <testing-utils/use_catch.h>

TEST_CASE(
  "bits2expr reconstructs empty structs and arrays",
  "[core][util][simplify_utils][zst-bits2expr]")
{
  const struct_typet empty;
  const unsignedbv_typet count_type{64};
  for(const bool little_endian : {false, true})
  {
    const auto value = bits2expr("", empty, little_endian, empty_namespace);
    REQUIRE(value.has_value());
    REQUIRE(*value == struct_exprt{{}, empty});
    REQUIRE(expr2bits(*value, little_endian, empty_namespace) == "");

    for(const unsigned count : {0u, 1u, 2u})
    {
      const array_typet type{empty, from_integer(count, count_type)};
      const auto array = bits2expr("", type, little_endian, empty_namespace);
      REQUIRE(array.has_value());
      REQUIRE(array->id() == ID_array);
      REQUIRE(array->type() == type);
      REQUIRE(array->operands().size() == count);
      for(const auto &element : array->operands())
        REQUIRE(element == struct_exprt{{}, empty});
      REQUIRE(expr2bits(*array, little_endian, empty_namespace) == "");
      REQUIRE_FALSE(
        bits2expr("1", type, little_endian, empty_namespace).has_value());
    }
  }
}

TEST_CASE(
  "bits2expr reconstructs nested zero-width arrays",
  "[core][util][simplify_utils][zst-bits2expr]")
{
  const unsignedbv_typet count_type{64};
  const struct_typet empty;
  const array_typet empty_inner{empty, from_integer(3, count_type)};
  const array_typet zero_length_inner{
    unsignedbv_typet{8}, from_integer(0, count_type)};
  for(const bool little_endian : {false, true})
  {
    for(const auto &inner : {empty_inner, zero_length_inner})
    {
      const array_typet outer{inner, from_integer(2, count_type)};
      const auto value = bits2expr("", outer, little_endian, empty_namespace);
      REQUIRE(value.has_value());
      REQUIRE(value->id() == ID_array);
      REQUIRE(value->type() == outer);
      REQUIRE(value->operands().size() == 2);
      for(const auto &row : value->operands())
      {
        REQUIRE(row.id() == ID_array);
        REQUIRE(row.type() == inner);
        REQUIRE(row.operands().size() == (inner == empty_inner ? 3 : 0));
        for(const auto &element : row.operands())
          REQUIRE(element == struct_exprt{{}, empty});
      }
      REQUIRE(expr2bits(*value, little_endian, empty_namespace) == "");
    }
  }
}

TEST_CASE(
  "bits2expr preserves tagged zero-width elements and nonzero siblings",
  "[core][util][simplify_utils][zst-bits2expr]")
{
  const cmdlinet cmdline;
  config.set(cmdline);
  symbol_tablet symbol_table;
  symbolt empty_symbol{"tag-E", struct_typet{}, ID_C};
  empty_symbol.is_type = true;
  REQUIRE_FALSE(symbol_table.add(empty_symbol));
  const namespacet ns{symbol_table};
  const struct_tag_typet empty_tag{"tag-E"};
  const array_typet array_type{
    empty_tag, from_integer(2, unsignedbv_typet{64})};
  const struct_exprt empty_element{{}, empty_tag};
  const array_exprt empty_array{{empty_element, empty_element}, array_type};
  const unsignedbv_typet byte_type{8};
  const unsignedbv_typet word_type{32};
  const struct_typet wrapper{
    {{"head", byte_type},
     {"z", array_type},
     {"x", word_type},
     {"tail", byte_type}}};
  const struct_exprt expected{
    {from_integer(0x5a, byte_type),
     empty_array,
     from_integer(0x12345678, word_type),
     from_integer(0xa5, byte_type)},
    wrapper};
  const union_typet union_type{{{"too_small", byte_type}, {"w", wrapper}}};

  for(const bool little_endian : {false, true})
  {
    const auto bits = expr2bits(expected, little_endian, ns);
    REQUIRE(bits.has_value());
    REQUIRE(bits->size() == 48);
    const auto restored = bits2expr(*bits, wrapper, little_endian, ns);
    REQUIRE(restored.has_value());
    REQUIRE(*restored == expected);
    REQUIRE(expr2bits(*restored, little_endian, ns) == bits);

    const auto restored_union = bits2expr(*bits, union_type, little_endian, ns);
    REQUIRE(restored_union.has_value());
    REQUIRE(*restored_union == union_exprt{"w", expected, union_type});
    REQUIRE(expr2bits(*restored_union, little_endian, ns) == bits);
  }
}
