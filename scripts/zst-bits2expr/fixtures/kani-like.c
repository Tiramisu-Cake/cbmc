// CBMC C model only; this is not a Kani/Rust replay.
#include <string.h>
struct E {};
struct PaddedZst { struct E z[2]; unsigned char padding[8]; };
union ArrayUnion {
  struct PaddedZst zst_array;
  unsigned char bytes[8];
};
int main(void) {
  union ArrayUnion src, dst;
  memset(&src, 0x5a, sizeof src);
  __CPROVER_assert(sizeof src == 8, "padded union extent");
  dst = *(union ArrayUnion *)&src;
  for(unsigned i = 0; i < 8; ++i)
    __CPROVER_assert(dst.bytes[i] == 0x5a, "padded union payload");
  return 0;
}
