#ifndef PROC_H
#define PROC_H

#include "types.h"

// Each process owns dynamically allocated user pages, page tables and kernel stack.
enum proc_state { PROC_UNUSED = 0, PROC_RUNNING = 1, PROC_EXITED = 2,
                  PROC_RUNNABLE = 3, PROC_WAITING = 4 };

struct proc {
  uint64 pid;
  uint64 *pagetable;
  uint64 state;
  uint64 exit_status; // Sign-extended int status stored in a 64-bit slot.
  uint64 parent_pid;
  uint64 wait_address;
  uint64 sz, heap_base, guard;
  uint64 kernel_stack;
  struct trapframe *frame;
  uint64 image_size;
};

struct proc *myproc(void);
void proc_boot_init(void);
void proc_exit(int status) __attribute__((noreturn));
void proc_shell_launch(void) __attribute__((noreturn));
int proc_fork(void);
uint64 proc_sbrk(int n);
void proc_reap_deferred(void);
void proc_yield(int restart_read);
int proc_exec(uint64 name_address);
int proc_wait(uint64 status_address);

#endif
