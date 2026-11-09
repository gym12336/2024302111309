#ifndef PROC_H
#define PROC_H

#include "types.h"
#include "spinlock.h"

// Byte-for-byte ABI with the immutable course swtch.S.
struct context {
  uint64 ra, sp;
  uint64 s0, s1, s2, s3, s4, s5, s6, s7, s8, s9, s10, s11;
};
#define CTX_OFFSET(field, offset) \
  _Static_assert(__builtin_offsetof(struct context, field) == offset, "context " #field)
CTX_OFFSET(ra, 0); CTX_OFFSET(sp, 8);
CTX_OFFSET(s0, 16); CTX_OFFSET(s1, 24); CTX_OFFSET(s2, 32);
CTX_OFFSET(s3, 40); CTX_OFFSET(s4, 48); CTX_OFFSET(s5, 56);
CTX_OFFSET(s6, 64); CTX_OFFSET(s7, 72); CTX_OFFSET(s8, 80);
CTX_OFFSET(s9, 88); CTX_OFFSET(s10, 96); CTX_OFFSET(s11, 104);
_Static_assert(sizeof(struct context) == 112, "context size");
#undef CTX_OFFSET

struct cpu {
  struct context context;
  struct proc *proc;
  int noff, intena;
};
enum proc_state { PROC_UNUSED, PROC_USED, PROC_RUNNABLE, PROC_RUNNING,
                  PROC_SLEEPING, PROC_ZOMBIE };
struct proc {
  struct spinlock lock;
  uint64 pid;
  enum proc_state state;
  int exit_status, killed;
  struct proc *parent; // wait_lock protects this relation.
  void *chan;
  struct context context;
  uint64 *pagetable;
  uint64 sz, heap_base, guard, kernel_stack, image_size;
  struct trapframe *frame;
  int cpu_ticks, last_slice_ticks, tickets;
  int base_priority, priority, ready_ticks;
};
struct cpu *mycpu(void);
struct proc *myproc(void);
void proc_boot_init(void);
void proc_exit(int) __attribute__((noreturn));
void proc_shell_launch(void) __attribute__((noreturn));
void scheduler(void) __attribute__((noreturn));
void sched(void);
void yield(void);
void sleep(void *, struct spinlock *);
void wakeup(void *);
void proc_clock(void);
void proc_user_tick(void);
int proc_pause(int);
uint64 proc_uptime(void);
int proc_kill(int);
int proc_killed(void);
int proc_schedstat(int, uint64, uint64);
int proc_setickets(int);
int proc_setpriority(int);
int proc_fork(void);
uint64 proc_sbrk(int);
int proc_exec(uint64);
int proc_wait(uint64);

#endif
