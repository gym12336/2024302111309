#include "kernel/types.h"
#include "user/user.h"

static volatile int value = 17;

int main(void)
{
  int parent = getpid();
  if (wait(0) != -1 || exec("missing", 0) != -1 || exec((char *)0x3fffffe000, 0) != -1) {
    printf("PROCTEST FAIL early\n"); exit(1);
  }
  int child = fork();
  if (child < 0) { printf("PROCTEST FAIL fork\n"); exit(1); }
  if (child == 0) {
    value = 99;
    if (getpid() == parent) exit(10);
    exit(-3);
  }
  if (wait((int *)0x3fffffe000) != -1) {
    printf("PROCTEST FAIL pointer\n"); exit(1);
  }
  int status = 0;
  if (wait(&status) != child || status != -3 || value != 17 || wait(0) != -1) {
    printf("PROCTEST FAIL isolation/status\n"); exit(1);
  }
  for (int i = 0; i < 8; i++) {
    child = fork();
    if (child < 0) { printf("PROCTEST FAIL reuse\n"); exit(1); }
    if (child == 0) exit(i);
    if (wait(&status) != child || status != i) {
      printf("PROCTEST FAIL reuse/status\n"); exit(1);
    }
  }
  int ids[2];
  for (int i = 0; i < 2; i++) {
    int id = fork();
    if (id < 0) { printf("PROCTEST FAIL capacity\n"); exit(1); }
    if (id == 0) exit(20 + i);
    ids[i] = id;
  }
  if (fork() != -1) { printf("PROCTEST FAIL full\n"); exit(1); }
  for (int i = 0; i < 2; i++) {
    if (wait(&status) != ids[i] || status != 20 + i) {
      printf("PROCTEST FAIL capacity/status\n"); exit(1);
    }
  }
  printf("PROCTEST PASS: fork isolation, signed status, wait errors, exec errors, slot reuse, capacity\n");
  exit(0);
}
