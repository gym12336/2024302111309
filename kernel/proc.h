#ifndef PROC_H
#define PROC_H

#include "types.h"

// Minimal identity for the single boot task; scheduling is not implemented yet.
struct proc {
  uint64 pid;
  uint64 *pagetable;
};

struct proc *myproc(void);
void proc_boot_init(void);

#endif
