#include "trapframe.h"
#include "riscv.h"
#include "memlayout.h"
#include "trap.h"

extern void printf(const char *format, ...);
extern char trampoline[], uservec[], userret[], kernel_trap_entry[];
static uint64 active_user_satp;

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
  w_stvec((uint64)kernel_trap_entry);
  // epc and user registers will be set when the first user task is created.
}

static void __attribute__((noreturn))
stop_trap(const char *kind)
{
  intr_off();
  printf("%s: scause=%lx sepc=%lx stval=%lx\n",
         kind, r_scause(), r_sepc(), r_stval());
  for (;;)
    asm volatile("wfi");
}

void
kerneltrap_stop(void)
{
  stop_trap("unexpected kernel trap");
}

static void
handle_user_trap(void)
{
  struct trapframe *tf = (struct trapframe *)TRAPFRAME;
  if (r_sstatus() & SSTATUS_SPP)
    stop_trap("usertrap called from supervisor mode");

  // Once in the kernel, a new kernel fault must not reuse uservec.
  w_stvec((uint64)kernel_trap_entry);
  tf->epc = r_sepc();
  uint64 cause = r_scause();
  if (cause == 8) {
    // ecall is always 32 bits, even when compressed instructions are enabled.
    tf->epc += 4;
    // Stage two will dispatch tf->a7 and arguments; unsupported calls fail now.
    tf->a0 = (uint64)-1;
  } else if (cause == ((1UL << 63) | 9)) {
    // UART/PLIC handling is added in stage three. Never silently ignore it.
    stop_trap("user external interrupt not connected yet");
  } else {
    stop_trap("unexpected user trap");
  }
}

static void
prepare_return(void)
{
  struct trapframe *tf = (struct trapframe *)TRAPFRAME;
  // No interrupt may enter uservec while we still hold kernel registers.
  intr_off();
  tf->kernel_satp = r_satp();
  tf->kernel_sp = (uint64)(trap_stack + sizeof(trap_stack));
  tf->kernel_trap = (uint64)usertrap;
  tf->kernel_hartid = r_tp();
  w_stvec(TRAMPOLINE + ((uint64)uservec - (uint64)trampoline));

  uint64 status = r_sstatus();
  status &= ~SSTATUS_SPP;
  status |= SSTATUS_SPIE;
  w_sstatus(status);
  w_sepc(tf->epc);
}

void
usertrapret(uint64 user_satp)
{
  // The first user launch supplies this; subsequent traps return to that map.
  active_user_satp = user_satp;
  prepare_return();
  uint64 entry = TRAMPOLINE + ((uint64)userret - (uint64)trampoline);
  ((void (*)(uint64))entry)(user_satp);
  __builtin_unreachable(); // userret ends in sret, not an ordinary C return.
}

void
usertrap(void)
{
  handle_user_trap();
  usertrapret(active_user_satp);
}
