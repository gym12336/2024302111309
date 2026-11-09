#include "common.h"

int main(void)
{
  int cpu = -1, slice = -1;
  ASSERT(schedstat(-1, &cpu, &slice) == 0 && cpu >= 0 && slice >= 0,
         "schedstat self");
  ASSERT(schedstat(0x7fffffff, &cpu, &slice) == -1, "schedstat missing PID");
  ASSERT(schedstat(-2, &cpu, &slice) == -1, "schedstat invalid PID");
  ASSERT(schedstat(-1, (int *)0xffffffffffffffffUL, &slice) == -1,
         "schedstat invalid CPU pointer");
  ASSERT(schedstat(-1, &cpu, (int *)0xffffffffffffffffUL) == -1,
         "schedstat invalid slice pointer");
  ASSERT(setickets(0) == -1 && setickets(-1) == -1 && setickets(17) == 0,
         "setickets bounds");
  ASSERT(setpriority(-1) == -1 && setpriority(2) == -1,
         "setpriority bounds");
  int old = setpriority(0);
  ASSERT(old >= 0 && setpriority(1) == 0 && setpriority(old) == 1,
         "setpriority returns previous base");
  ASSERT(pause(-1) == -1 && pause(0) == 0, "pause bounds");
  unsigned long t = time_rdtime();
  int ticks = uptime();
  ASSERT(pause(5) == 0 && uptime() - ticks >= 5 && time_rdtime() > t,
         "pause must sleep for ticks, time must advance");

  int pid = fork();
  ASSERT(pid >= 0, "fork status child");
  if (pid == 0) exit(-37);
  int status = 0;
  // Leave the child as ZOMBIE briefly: observation must reject exited PIDs.
  pause(4);
  ASSERT(schedstat(pid, &cpu, &slice) == -1, "schedstat zombie");
  ASSERT(wait((int *)0xffffffffffffffffUL) == -1, "wait bad status pointer");
  ASSERT(wait(&status) == pid && status == -37, "signed exit status and retry");
  ASSERT(wait(0) == -1, "wait no child");
  ASSERT(schedstat(pid, &cpu, &slice) == -1, "schedstat reaped PID");

  pid = fork();
  ASSERT(pid >= 0, "fork kill child");
  if (pid == 0) { pause(1000); exit(0); }
  pause(2);
  t = time_rdtime();
  ASSERT(kill(pid) == 0, "kill sleeping child");
  ASSERT(wait(&status) == pid && status == -1, "kill wakes and exits child");
  ASSERT(time_rdtime() - t < 10000000UL, "killed sleeper stayed asleep");
  ASSERT(kill(0x7fffffff) == -1, "kill missing child");
  printf("RESULT sched_abi = self,pointers,tickets,priority,pause,zombie,wait,kill\n");
  PASS("schedcheck");
}
