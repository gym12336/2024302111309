#include "common.h"

static int children[2];

static void cleanup(void)
{
  for (int i = 0; i < 2; i++)
    if (children[i] > 0) kill(children[i]);
  while (wait(0) > 0) ;
  children[0] = children[1] = 0;
}

static void check(int condition, const char *message)
{
  if (!condition) {
    cleanup();
    printf("FAIL: priority %s\n", message);
    exit(1);
  }
}

static int spawn(int priority, int delay, unsigned long deadline)
{
  int pid = fork();
  if (pid == 0) {
    if (setpriority(priority) < 0 || pause(delay) < 0) exit(2);
    burn_until(deadline);
    exit(0);
  }
  return pid;
}

int main(void)
{
  check(setpriority(1) >= 0, "observer priority");

  // Case 1: a low process gets service through aging, while high dominates.
  unsigned long deadline = deadline_after(130);
  children[0] = spawn(1, 4, deadline);
  children[1] = spawn(0, 4, deadline);
  check(children[0] > 0 && children[1] > 0, "fork share case");
  pause(8);
  int h0 = cpu_of(children[0]), l0 = cpu_of(children[1]);
  pause(64);
  int high = cpu_of(children[0]), low = cpu_of(children[1]);
  check(h0 >= 0 && l0 >= 0 && high >= h0 && low >= l0, "share sampling");
  high -= h0; low -= l0;
  printf("RESULT priority_cpu = %d:%d\n", high, low);
  check(high + low > 32, "too few CPU ticks");
  check(low > 0, "low priority starved");
  check(high > 2 * low, "priority boundary missing");
  cleanup();

  // Case 2: on its first dispatch the low worker lowers its own priority.
  // The second user timer tick yields it. It can observe those two ticks
  // only after it is dispatched again, which requires at least 8 READY ticks
  // while the high worker stays runnable. With round robin it resumes early;
  // without aging it cannot resume before the high worker's deadline.
  deadline = deadline_after(100);
  children[0] = spawn(1, 0, deadline);
  children[1] = fork();
  if (children[1] == 0) {
    if (setpriority(0) < 0) exit(1);
    int before = cpu_of(-1), start = uptime(), current = before;
    if (before < 0) exit(1);
    while (current - before < 2) {
      for (volatile int i = 0; i < 200000; i++) ;
      current = cpu_of(-1);
      if (current < 0) exit(1);
    }
    exit(uptime() - start);
  }
  check(children[0] > 0 && children[1] > 0, "fork aging case");
  int elapsed = -1, reaped = wait(&elapsed);
  if (reaped == children[1]) children[1] = 0;
  if (reaped == children[0]) children[0] = 0;
  printf("RESULT aging_two_cpu_ticks_elapsed = %d ticks\n", elapsed);
  check(children[1] == 0 && children[0] > 0, "low worker must finish before high");
  check(elapsed >= 10 && elapsed <= 18, "two CPU ticks plus eight READY ticks");
  cleanup();

  // Same-priority ties must rotate rather than favoring the lowest table slot.
  deadline = deadline_after(90);
  children[0] = spawn(1, 2, deadline);
  children[1] = spawn(1, 2, deadline);
  check(children[0] > 0 && children[1] > 0, "fork round-robin case");
  pause(48);
  high = cpu_of(children[0]); low = cpu_of(children[1]);
  printf("RESULT equal_priority_cpu = %d:%d\n", high, low);
  check(high > 8 && low > 8, "same-priority starvation");
  check(high <= 2 * low && low <= 2 * high, "same-priority fairness");
  cleanup();
  PASS("priority ID9");
}
