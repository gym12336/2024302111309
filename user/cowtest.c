#include "kernel/types.h"
#include "kernel/course_sid.h"
#include "kernel/riscv.h"
#include "kernel/smp_stats.h"
#include "user/user.h"

#define WRITE_ROUNDS 6
#define WORKERS 8
#define WORK_PAGES 16
#define BUDGET_PAGES (LAB5_COW_BUDGET + 8)
#define ARGV_STATUS 47

static void
check(int condition, const char *message)
{
  if (!condition) {
    fprintf(2, "COWTEST FAIL: %s\n", message);
    exit(1);
  }
}

static uint64
free_pages(void)
{
  struct smp_stats stats;
  check(smpstat(&stats) == 0, "read physical page count");
  return stats.free_pages;
}

static volatile int *
alloc_pages(int count)
{
  char *address = sbrk(count * PGSIZE);
  check(address != SBRK_ERROR, "allocate test pages");
  return (volatile int *)address;
}

static void
set_pages(volatile int *pages, int count, int seed)
{
  for (int i = 0; i < count; i++)
    pages[i * (PGSIZE / sizeof(*pages))] = seed + i;
}

static void
check_pages(volatile int *pages, int count, int seed, const char *message)
{
  for (int i = 0; i < count; i++)
    check(pages[i * (PGSIZE / sizeof(*pages))] == seed + i, message);
}

static void
check_reclaimed(uint64 initial)
{
  check(pmc(1) == 0, "all shared page references released");
  check(free_pages() == initial, "all detached pages reclaimed");
}

static void
check_writes(void)
{
  volatile int *page = alloc_pages(1);
  uint64 initial = free_pages();
  *page = 17;
  for (int round = 0; round < WRITE_ROUNDS; round++) {
    int original = *page, status;
    volatile int stack_value = original;
    unsigned long long before = pmc(0);
    int child = fork();
    check(child >= 0, "fork alternating writer");
    if (child == 0) {
      stack_value += 1;
      check(stack_value == original + 1 && *page == original, "child inherits data");
      *page = original + 100;
      check(*page == original + 100, "child first write");
      *page = original + 200;
      check(*page == original + 200, "child second write");
      exit(23);
    }
    stack_value += 2;
    check(wait(&status) == child && status == 23, "reap alternating writer");
    check(stack_value == original + 2 && *page == original, "parent retains data");
    *page = original + 1;
    check(*page == original + 1, "parent writes after child");
    check(pmc(0) - before == 2, "one stack and one heap copy per round");
    check_reclaimed(initial);
  }

  // Only wait writes the heap page. The child still maps it as a zombie.
  page[1] = 0;
  volatile int stack_value = 0;
  unsigned long long before = pmc(0);
  int child = fork();
  check(child >= 0, "fork copyout reader");
  if (child == 0) {
    stack_value = 1;
    check(stack_value == 1 && page[1] == 0, "child sees original wait status area");
    exit(57);
  }
  stack_value = 2;
  check(wait((int *)&page[1]) == child && page[1] == 57, "wait writes shared COW page");
  check(pmc(0) - before == 2, "copyout detaches heap page once");
  check_reclaimed(initial);
  check(sbrk(-PGSIZE) != SBRK_ERROR, "release alternating write page");
  printf("COWTEST PASS: %d alternating rounds, exact copies and kernel copyout\n", WRITE_ROUNDS);
}

static void
wait_until(int deadline)
{
  int delay = deadline - uptime();
  if (delay > 0)
    check(pause(delay) == 0, "synchronize writers");
}

static void
check_concurrent_writes(void)
{
  volatile int *pages = alloc_pages(WORK_PAGES);
  uint64 initial = free_pages();
  int children[WORKERS];
  set_pages(pages, WORK_PAGES, 100);
  int deadline = uptime() + 8;
  for (int i = 0; i < WORKERS; i++) {
    int child = fork();
    check(child >= 0, "fork concurrent writer");
    if (child == 0) {
      wait_until(deadline);
      check_pages(pages, WORK_PAGES, 100, "concurrent child inherits data");
      int seed = 200 + i * WORK_PAGES;
      set_pages(pages, WORK_PAGES, seed);
      check(pause(2) == 0, "concurrent writer pause");
      check_pages(pages, WORK_PAGES, seed, "concurrent child retains private data");
      exit(i + 1);
    }
    children[i] = child;
  }
  check(pmc(1) > 0, "unreaped workers still share mapped pages");
  wait_until(deadline);
  check_pages(pages, WORK_PAGES, 100, "concurrent parent retains inherited data");
  set_pages(pages, WORK_PAGES, 400);
  for (int i = 0; i < WORKERS; i++) {
    int status;
    int child = wait(&status);
    check(child > 0 && status >= 1 && status <= WORKERS, "reap concurrent writer");
    check(child == children[status - 1], "reap each successful writer once");
    children[status - 1] = 0;
  }
  check(wait(0) == -1, "no concurrent child left");
  check_pages(pages, WORK_PAGES, 400, "concurrent parent retains private data");
  check_reclaimed(initial);
  check(sbrk(-WORK_PAGES * PGSIZE) != SBRK_ERROR, "release concurrent write pages");
  printf("COWTEST PASS: %d concurrent writers, shared pages returned to zero\n", WORKERS);
}

static void
check_readonly_fault(void)
{
  uint64 initial = free_pages();
  int status;
  int child = fork();
  check(child >= 0, "fork read-only fault child");
  if (child == 0) {
    // The image is linked at zero. Use a real store, without a C null dereference.
    asm volatile("sb zero, 0(zero)" ::: "memory");
    exit(77);
  }
  check(wait(&status) == child && status == -1, "write to .text kills only the child");
  check_reclaimed(initial);
  printf("COWTEST PASS: write to read-only text killed the child\n");
}

static void
check_budget(void)
{
  volatile int *pages = alloc_pages(BUDGET_PAGES);
  uint64 initial = free_pages();
  set_pages(pages, BUDGET_PAGES, 1000);
  unsigned long long before = pmc(0);
  int child = fork();
  check(child >= 0, "fork COW budget writer");
  if (child == 0) {
    set_pages(pages, BUDGET_PAGES, 2000);
    check_pages(pages, BUDGET_PAGES, 2000, "writes beyond the COW budget succeed");
    exit(0);
  }
  int status;
  check(wait(&status) == child && status == 0, "COW budget writer survives");
  check_pages(pages, BUDGET_PAGES, 1000, "budget writer keeps parent data intact");
  unsigned long long copies = pmc(0) - before;
  check(copies >= BUDGET_PAGES, "actual copying exceeds the per-process budget");
  check_reclaimed(initial);
  check(sbrk(-BUDGET_PAGES * PGSIZE) != SBRK_ERROR, "release budget write pages");
  printf("COWTEST PASS: budget %d, %d heap pages written, %llu copies\n",
         LAB5_COW_BUDGET, BUDGET_PAGES, copies);
}

static void
check_arg_probe(int argc, char **argv)
{
  check(argc == 4 && argv && (uint64)argv % 16 == 0, "exec argc and argv alignment");
  check(argv[4] == 0, "exec argv NULL sentinel");
  for (int i = 0; i < argc; i++)
    check(argv[i] && (uint64)argv[i] % 16 == 0, "exec argument string alignment");
  check(strcmp(argv[0], "cowtest") == 0 && strcmp(argv[1], "--argv-probe") == 0 &&
        strcmp(argv[2], "copied across a page") == 0 && argv[3][0] == 0,
        "exec preserves argument strings including an empty one");
  exit(ARGV_STATUS);
}

static void
check_exec(void)
{
  uint64 initial = free_pages();
  char *area = (char *)alloc_pages(2);
  char *across = area + PGSIZE - 5;
  strcpy(across, "copied across a page");
  char *args[] = {"cowtest", "--argv-probe", across, "", 0};
  int child = fork();
  check(child >= 0, "fork exec argv probe");
  if (child == 0) {
    exec("cowtest", args);
    check(0, "valid exec must return to a new image");
  }
  int status;
  check(wait(&status) == child && status == ARGV_STATUS, "exec argv probe exits successfully");

  check(exec((const char *)MAXVA, args) == -1, "reject invalid exec path pointer");
  check(exec("cowtest", (char **)MAXVA) == -1, "reject invalid exec argv pointer");
  args[2] = (char *)MAXVA;
  check(exec("cowtest", args) == -1, "reject invalid exec string pointer");

  char **missing_end = (char **)(area + 2 * PGSIZE - sizeof(char *));
  *missing_end = "cowtest";
  check(exec("cowtest", missing_end) == -1, "reject argv crossing into an unmapped page");
  char *unterminated = area + 2 * PGSIZE - 8;
  memset(unterminated, 'x', 8);
  args[2] = unterminated;
  check(exec("cowtest", args) == -1, "reject unterminated argument at page boundary");

  char *too_many[MAXARG + 2];
  for (int i = 0; i <= MAXARG; i++)
    too_many[i] = "arg";
  too_many[MAXARG + 1] = 0;
  check(exec("cowtest", too_many) == -1, "reject too many exec arguments");
  check(strcmp(across, "copied across a page") == 0, "failed exec preserves the old image");
  check(sbrk(-2 * PGSIZE) == area + 2 * PGSIZE, "release exec test pages");
  check_reclaimed(initial);
  printf("COWTEST PASS: exec argv alignment, strings and invalid pointers\n");
}

int
main(int argc, char **argv)
{
  if (argc != 1)
    check_arg_probe(argc, argv);
  check(argv && argv[0] && argv[1] == 0 && strcmp(argv[0], "cowtest") == 0,
        "shell passes the program name");
  check(pmc(-1) == (unsigned long long)-1 && pmc(2) == (unsigned long long)-1,
        "reject unsupported PMC counters");
  uint64 initial = free_pages();
  check_writes();
  check_concurrent_writes();
  check_readonly_fault();
  check_budget();
  check_exec();
  check_reclaimed(initial);
  printf("COWTEST PASS: all five checks\n");
  exit(0);
}
