#ifndef PROC_H
#define PROC_H

#include "types.h"

// Minimal record for the single boot task; scheduling is not implemented yet.
enum proc_state { PROC_UNUSED = 0, PROC_RUNNING = 1, PROC_EXITED = 2 };

struct proc {
  uint64 pid;
  uint64 *pagetable;
  uint64 state;
  uint64 exit_status; // Sign-extended int status stored in a 64-bit slot.
};

struct proc *myproc(void);
void proc_boot_init(void);
void proc_exit(int status) __attribute__((noreturn));

#endif
