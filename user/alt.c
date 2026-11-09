#include "kernel/types.h"
#include "user/user.h"

// Finite compute-bound siblings make timer preemption visible at the terminal.
static void run(char c)
{
  for (int i = 0; i < 16; i++) {
    for (volatile int d = 0; d < 1500000; d++)
      ;
    write(1, &c, 1);
  }
  exit(0);
}

int main(void)
{
  int a = fork();
  if (a == 0) run('A');
  int b = fork();
  if (b == 0) run('B');
  if (a < 0 || b < 0) {
    if (a > 0) kill(a);
    if (b > 0) kill(b);
    while (wait(0) > 0) ;
    printf("\nFAIL: alt fork\n");
    exit(1);
  }
  int status;
  for (int i = 0; i < 2; i++) {
    if (wait(&status) < 0 || status != 0) {
      printf("\nFAIL: alt wait\n");
      exit(1);
    }
  }
  printf("\nalt done\nPASS: alt\n");
  exit(0);
}
