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
  unsigned char a[4];
  unsigned char b[4];
};

int main(void)
{
  unsigned char buf[sizeof(struct W)];
  memset(buf, 0x5a, sizeof buf);
  __CPROVER_assert(sizeof(struct W) == 8, "wrapper size");
  struct W w = *(struct W *)buf;
  for(unsigned i = 0; i < 4; ++i)
  {
    __CPROVER_assert(w.a[i] == 0x5a, "a preserved");
    __CPROVER_assert(w.b[i] == 0x5a, "b preserved");
  }
  return 0;
}
