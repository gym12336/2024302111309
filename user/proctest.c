#include "kernel/types.h"
#include "kernel/param.h"
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
  // The shell and this test own two slots. Zombies retain the remaining
  // slots until wait reaps them; NPROC replaces Lab2's fixed four-slot limit.
  int ids[NPROC], seen[NPROC];
  for (int i = 0; i < NPROC - 2; i++) {
    int id = fork();
    if (id < 0) { printf("PROCTEST FAIL capacity\n"); exit(1); }
    if (id == 0) exit(20 + i);
    ids[i] = id;
    seen[i] = 0;
  }
  if (fork() != -1) { printf("PROCTEST FAIL full\n"); exit(1); }
  for (int i = 0; i < NPROC - 2; i++) {
    int reaped = wait(&status), match = -1;
    for (int j = 0; j < NPROC - 2; j++)
      if (ids[j] == reaped) match = j;
    if (match < 0 || seen[match] || status != 20 + match) {
      printf("PROCTEST FAIL capacity/status\n"); exit(1);
    }
    seen[match] = 1;
  }
  if (wait(0) != -1) { printf("PROCTEST FAIL capacity/reap\n"); exit(1); }
  printf("PROCTEST PASS: fork isolation, signed status, wait errors, exec errors, slot reuse, capacity\n");
  exit(0);
}
