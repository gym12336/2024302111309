#include "proc.h"
#include "riscv.h"

extern void proc_exit_idle(void) __attribute__((noreturn));

// The first user task is assigned PID 1. This is unrelated to the hart ID.
static struct proc boot_process;

void
proc_boot_init(void)
{
  boot_process.pid = 1;
  boot_process.state = PROC_RUNNING;
  boot_process.exit_status = 0;
}

struct proc *
myproc(void)
{
  return &boot_process;
}

void
proc_exit(int status)
{
  intr_off();
  struct proc *p = myproc();
  p->exit_status = (uint64)(long)status;
  p->state = PROC_EXITED;
  // No scheduler or parent yet: keep the record and remain in kernel mode.
  proc_exit_idle();
}
