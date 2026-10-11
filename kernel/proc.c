#include "proc.h"

// The first user task is assigned PID 1. This is unrelated to the hart ID.
static struct proc boot_process;

void
proc_boot_init(void)
{
  boot_process.pid = 1;
}

struct proc *
myproc(void)
{
  return &boot_process;
}
