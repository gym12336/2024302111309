#include "trapframe.h"
#include "riscv.h"

extern void printf(const char *format, ...);

// The trampoline needs a C destination. Full dispatch is a later lab2 step.
void
usertrap(void)
{
  printf("unexpected user trap: scause=%lx sepc=%lx stval=%lx\n",
         r_scause(), r_sepc(), r_stval());
  for (;;)
    asm volatile("wfi");
}
