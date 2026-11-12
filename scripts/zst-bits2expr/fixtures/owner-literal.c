#include <string.h>
struct E {};
struct W { struct E z[2]; char pad[8]; };

int main(void) {
  char buf[8];
  memset(buf, 0x5a, sizeof buf);
  struct W w = *(struct W *)buf;
  __CPROVER_assert(w.pad[0] == 0x5a, "copied");
  return 0;
}
