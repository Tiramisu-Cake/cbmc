// Author: Tiramisu-Cake <igkharin@gmail.com>
// GNU C empty structs have zero size.
#include <stddef.h>
#include <string.h>

struct E
{
};

struct W
{
  unsigned int before;
  struct E z[2];
  unsigned int x;
  unsigned char tail[4];
};

int main(void)
{
  union
  {
    struct W aligned;
    unsigned char bytes[sizeof(struct W)];
  } storage;
  memset(storage.bytes, 0x5a, sizeof storage);
  __CPROVER_assert(sizeof(unsigned int) == 4, "target int size");
  __CPROVER_assert(sizeof(struct W) == 12, "wrapper size");
  __CPROVER_assert(offsetof(struct W, x) == 4, "interior offset");
  struct W w = *(struct W *)storage.bytes;
  __CPROVER_assert(w.before == 0x5a5a5a5au, "before preserved");
  __CPROVER_assert(w.x == 0x5a5a5a5au, "x preserved");
  for(unsigned i = 0; i < sizeof w.tail; ++i)
    __CPROVER_assert(w.tail[i] == 0x5a, "tail preserved");
  return 0;
}
