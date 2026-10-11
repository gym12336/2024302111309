#ifndef PROC_H
#define PROC_H

#include "types.h"

// Minimal identity for the single boot task; scheduling is not implemented yet.
struct proc {
  uint64 pid;
};

struct proc *myproc(void);
void proc_boot_init(void);

#endif
