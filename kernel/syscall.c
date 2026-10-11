#include "syscall_dispatch.h"
#include "syscall.h"
#include "proc.h"

static uint64
sys_getpid(void)
{
  return myproc()->pid;
}

uint64
syscall_dispatch(struct trapframe *tf)
{
  // Compare the full 64-bit register, so large invalid numbers cannot alias 11.
  switch (tf->a7) {
  case SYS_getpid:
    return sys_getpid();
  default:
    return (uint64)-1;
  }
}
