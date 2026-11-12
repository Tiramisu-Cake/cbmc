// Author: Tiramisu-Cake <igkharin@gmail.com>
// GNU C empty structs have zero size.
#include <stddef.h>
#include <string.h>

struct E
{
};

struct W
{
  struct E z[2];
  unsigned char pad[8];
};

union U
{
  struct W w; // First arm that can represent all eight bytes.
  unsigned char bytes[8];
};

int main(void)
{
  union U storage;
  memset(storage.bytes, 0x5a, sizeof storage);
  __CPROVER_assert(sizeof(union U) == 8, "union size");
  union U copied = *(union U *)storage.bytes;
  for(unsigned i = 0; i < sizeof copied.w.pad; ++i)
    __CPROVER_assert(copied.w.pad[i] == 0x5a, "union payload bytes");
  return 0;
}
