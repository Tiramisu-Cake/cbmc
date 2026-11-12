// Author: Tiramisu-Cake <igkharin@gmail.com>
// GNU C empty structs have zero size.
#include <stddef.h>
#include <string.h>

struct E
{
};

struct W
{
  struct E z[2][3];
  unsigned char pad[8];
};

int main(void)
{
  unsigned char buf[sizeof(struct W)];
  memset(buf, 0x5a, sizeof buf);
  __CPROVER_assert(sizeof(struct E) == 0, "empty size");
  __CPROVER_assert(sizeof(struct W) == 8, "wrapper size");
  __CPROVER_assert(offsetof(struct W, pad) == 0, "pad offset");
  struct W w = *(struct W *)buf;
  for(unsigned i = 0; i < sizeof w.pad; ++i)
    __CPROVER_assert(w.pad[i] == 0x5a, "all payload bytes");
  return 0;
}
