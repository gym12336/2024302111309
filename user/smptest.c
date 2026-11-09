#include "common.h"
#include "kernel/smp_stats.h"

// The declaration is also exported by user.h after integrating the kernel ABI.
extern int smpstat(struct smp_stats *);

#define WORKERS 8
#define ROUNDS 3
#define PARENT_BYTES (5 * 4096 + 37)
#define WORK_BYTES (3 * 4096 + 13)

static volatile int private_value = 17;

static void check_bytes(char *bytes, int length, int value)
{
  for (int i = 0; i < length; i++)
    ASSERT((uchar)bytes[i] == (uchar)value, "private address space content");
}

static void fill_bytes(char *bytes, int length, int value)
{
  for (int i = 0; i < length; i++) bytes[i] = value;
}

static void worker(int index, char *heap, unsigned long deadline)
{
  ASSERT(private_value == 17, "fork inherited global data");
  check_bytes(heap, PARENT_BYTES, 0x35);
  private_value = 100 + index;
  fill_bytes(heap, PARENT_BYTES, 0x60 + index);
  char *extra = sbrk(WORK_BYTES);
  ASSERT(extra == heap + PARENT_BYTES, "concurrent sbrk grows own heap");
  fill_bytes(extra, WORK_BYTES, 0x20 + index);

  int child = fork();
  ASSERT(child >= 0, "concurrent nested fork");
  if (child == 0) {
    ASSERT(private_value == 100 + index, "nested fork inherited global");
    check_bytes(extra, WORK_BYTES, 0x20 + index);
    private_value = -1;
    fill_bytes(heap, PARENT_BYTES, 0x7e);
    fill_bytes(extra, WORK_BYTES, 0x7f);
    ASSERT(pause(1) == 0, "nested child pause");
    exit(-37);
  }
  int status = 0;
  ASSERT(wait((int *)0xffffffffffffffffUL) == -1, "bad wait pointer retains child");
  ASSERT(wait(&status) == child && status == -37, "nested signed status and wait retry");
  ASSERT(private_value == 100 + index, "nested global isolation");
  check_bytes(heap, PARENT_BYTES, 0x60 + index);
  check_bytes(extra, WORK_BYTES, 0x20 + index);

  child = fork();
  ASSERT(child >= 0, "concurrent exec fork");
  if (child == 0) {
    ASSERT(exec("does-not-exist", 0) == -1, "failed exec preserves address space");
    check_bytes(extra, WORK_BYTES, 0x20 + index);
    exec("hi", 0);
    ASSERT(0, "concurrent exec hi");
  }
  ASSERT(wait(&status) == child && status == 0, "concurrent exec and reap");
  ASSERT(pause(1 + index % 3) == 0, "worker pause and wakeup");
  burn_until(deadline);
  check_bytes(heap, PARENT_BYTES, 0x60 + index);
  check_bytes(extra, WORK_BYTES, 0x20 + index);
  ASSERT(sbrk(-WORK_BYTES) == extra + WORK_BYTES && sbrk(0) == extra,
         "concurrent sbrk shrink");
  ASSERT(wait(0) == -1, "worker reaped every descendant");
  exit(-100 - index);
}

int main(void)
{
  struct smp_stats initial, before, after;
  ASSERT(smpstat(&initial) == 0, "smpstat snapshot");
  ASSERT(initial.online_mask != 0 && (initial.online_mask & ~3UL) == 0,
         "initial online mask contains a supported hart");
  ASSERT(smpstat((struct smp_stats *)0xffffffffffffffffUL) == -1,
         "smpstat invalid destination");
  ASSERT(smpstat((struct smp_stats *)0) == -1, "smpstat read-only destination");
  char *heap = sbrk(PARENT_BYTES);
  ASSERT(heap != (char *)-1, "parent heap allocation");
  fill_bytes(heap, PARENT_BYTES, 0x35);
  ASSERT(smpstat(&before) == 0, "initial resource snapshot");

  unsigned long per_tick = tick_cycles();
  unsigned long start_time = time_rdtime();
  int start_ticks = uptime();
  for (int round = 0; round < ROUNDS; round++) {
    int ids[WORKERS], seen[WORKERS];
    unsigned long deadline = time_rdtime() + 40 * per_tick;
    for (int i = 0; i < WORKERS; i++) {
      int pid = fork();
      ASSERT(pid >= 0, "eight concurrent workers");
      if (pid == 0) worker(i, heap, deadline);
      ids[i] = pid;
      seen[i] = 0;
    }
    for (int i = 0; i < WORKERS; i++) {
      int status = 0, reaped = wait(&status), match = -1;
      for (int j = 0; j < WORKERS; j++) if (ids[j] == reaped) match = j;
      ASSERT(match >= 0 && !seen[match] && status == -100 - match,
             "all workers reaped once with signed statuses");
      seen[match] = 1;
    }
    ASSERT(wait(0) == -1, "parent has no leaked child");
    ASSERT(private_value == 17, "parent global isolation");
    check_bytes(heap, PARENT_BYTES, 0x35);
    ASSERT(smpstat(&after) == 0 && after.free_pages == before.free_pages,
           "fork exec exit wait return every allocated page");
    printf("RESULT smp_round = %d workers=%d free_pages=%lu\n",
           round + 1, WORKERS, after.free_pages);
  }

  int child = fork();
  ASSERT(child >= 0, "fork sleeping child");
  if (child == 0) { pause(1000); exit(0); }
  ASSERT(pause(2) == 0 && kill(child) == 0, "kill sleeping child");
  int status = 0;
  unsigned long kill_time = time_rdtime();
  ASSERT(wait(&status) == child && status == -1, "killed sleeper wakes and exits");
  ASSERT(time_rdtime() - kill_time < 10000000UL, "kill wait finishes within one second");
  ASSERT(sbrk(-PARENT_BYTES) == heap + PARENT_BYTES, "parent heap shrink");
  ASSERT(smpstat(&after) == 0 && after.free_pages == initial.free_pages,
         "complete resource reclamation");
  ASSERT(after.online_mask == 1 || after.online_mask == 3,
         "final single or dual hart online mask");
  ASSERT((after.online_mask & initial.online_mask) == initial.online_mask,
         "initially online harts remain online");
  for (int hart = 0; hart < NCPU; hart++) {
    uint64 dispatches = after.dispatches[hart] - before.dispatches[hart];
    uint64 user_ticks = after.user_ticks[hart] - before.user_ticks[hart];
    if (after.online_mask & (1UL << hart)) {
      ASSERT(dispatches > 0 && user_ticks > 0, "every online hart executes user work");
      printf("RESULT smp_hart = %d dispatches=%lu user_ticks=%lu\n",
             hart, dispatches, user_ticks);
    } else {
      ASSERT(after.dispatches[hart] == 0 && after.user_ticks[hart] == 0,
             "offline harts have no scheduler or user ticks");
    }
  }
  int elapsed_ticks = uptime() - start_ticks;
  unsigned long elapsed_time = time_rdtime() - start_time;
  // QEMU virt's 10 MHz timebase and the configured 100000-cycle timer interval.
  // A second hart must not double the one global uptime clock.
  ASSERT(elapsed_ticks >= 20 && elapsed_time >= (unsigned long)elapsed_ticks * 80000 &&
         elapsed_time <= (unsigned long)elapsed_ticks * 120000,
         "global ticks advance once per interval on hart zero");
  printf("RESULT smp_clock = ticks=%d cycles=%lu\n", elapsed_ticks, elapsed_time);
  printf("RESULT smp_online = %lu reclaimed=%lu\n", after.online_mask, after.free_pages);
  printf("RESULT smp_stress = fork,exec,exit,wait,pause,sbrk,isolation,kill\n");
  PASS("smptest");
}
