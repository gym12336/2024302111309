#include "kernel/types.h"
#include "user/user.h"

// Planned before execution: cross-page write and explicit stack guard access.
int main(void)
{
  char *base = sbrk(8192);
  if (base == (char *)-1) exit(1);
  char *edge = base+4096-3;
  char text[] = "CROSS-PAGE PASS\n";
  for (int i=0; i<sizeof(text)-1; i++) edge[i]=text[i];
  if (write(1, edge, sizeof(text)-1) != sizeof(text)-1) exit(2);
  int pid = fork(), status = 0;
  if (pid == 0) {
    // heap starts immediately above the two-page stack; guard is the third page.
    *(volatile char *)(base-3*4096) = 1;
    exit(0);
  }
  if (pid < 0 || wait(&status) < 0 || status == 0) exit(3);
  printf("GUARD PASS\n");
  if (sbrk(-8192) != base+8192 || sbrk(0) != base) exit(4);
  printf("SHRINK PASS\n");
  if (exec("does-not-exist", 0) != -1) exit(5);
  printf("EXEC-FAIL PASS\n");
  int pages = 0;
  while (sbrk(4096) != (char *)-1) pages++;
  char *old = sbrk(0);
  if (fork() != -1 || exec("hi", 0) != -1 || sbrk(0) != old) exit(6);
  printf("OOM-FORK-EXEC PASS\n");
  if (sbrk(-pages*4096) != old || sbrk(0) != base) exit(7);
  char *unaligned = sbrk(1);
  if (unaligned != base || sbrk(4096) != base+1) exit(8);
  base[4096] = 42;
  if (sbrk(-4097) != base+4097 || sbrk(0) != base) exit(9);
  printf("UNALIGNED-SBRK PASS\n");
  exit(0);
}
