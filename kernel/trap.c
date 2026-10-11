#include "trapframe.h"
#include "riscv.h"
#include "memlayout.h"

extern void printf(const char *format, ...);
void usertrap(void);

// A separate stack for the first boot user task. Later processes need their own.
static uint8 trap_stack[2 * PGSIZE] __attribute__((aligned(16)));

void
trap_init(void)
{
  struct trapframe *tf = (struct trapframe *)TRAPFRAME;
  uint8 *bytes = (uint8 *)tf;
  for (uint64 i = 0; i < sizeof(*tf); i++)
    bytes[i] = 0;

  // These are inputs to uservec, so prepare them before entering user mode.
  tf->kernel_satp = r_satp();
  tf->kernel_sp = (uint64)(trap_stack + sizeof(trap_stack));
  tf->kernel_trap = (uint64)usertrap;
  tf->kernel_hartid = r_tp();
  // epc and user registers will be set when the first user task is created.
}

// The trampoline needs a C destination. Full dispatch is a later lab2 step.
void
usertrap(void)
{
  printf("unexpected user trap: scause=%lx sepc=%lx stval=%lx\n",
         r_scause(), r_sepc(), r_stval());
  for (;;)
    asm volatile("wfi");
}
