#include "kernel/types.h"
#include "user/user.h"
int main(void)
{
  int pid = fork();
  if (pid < 0) exit(1);
  if (pid == 0) { exec("spin", 0); exit(2); }
  printf("CONCURRENT shell and spin\n");
  exec("sh", 0);
  exit(3);
}
