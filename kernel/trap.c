#include "trapframe.h"
#include "riscv.h"
#include "memlayout.h"
#include "trap.h"
#include "syscall_dispatch.h"
#include "uart.h"
#include "plic.h"
#include "proc.h"

extern void printf(const char *format, ...);
extern char trampoline[], uservec[], userret[], kernel_trap_entry[];
static uint64 active_user_satp;
static volatile uint64 kernel_softirq_count;

// Legacy probe stack. Shell processes use their bank's private kernel stack.
static uint8 trap_stack[2 * PGSIZE] __attribute__((aligned(16)));

static uint64
kernel_stack_top(void)
{
  uint64 stack = myproc()->kernel_stack;
  return stack ? stack : (uint64)(trap_stack + sizeof(trap_stack));
}

void
trap_init(void)
{
  struct trapframe *tf = (struct trapframe *)TRAPFRAME;
  uint8 *bytes = (uint8 *)tf;
  for (uint64 i = 0; i < sizeof(*tf); i++)
    bytes[i] = 0;

  // These are inputs to uservec, so prepare them before entering user mode.
  tf->kernel_satp = r_satp();
  tf->kernel_sp = kernel_stack_top();
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
external_interrupt(void)
{
  int irq = plic_claim();
  if (irq == UART0_IRQ)
    uartintr();
  if (irq != 0)
    plic_complete(irq);
  if (irq != 0 && irq != UART0_IRQ) {
    printf("unexpected PLIC source=%d\n", irq);
    stop_trap("unexpected external interrupt");
  }
  // A stale notification can legitimately claim 0; do not complete ID 0.
}

void
kerneltrap(void)
{
  uint64 epc = r_sepc();
  uint64 status = r_sstatus();
  uint64 cause = r_scause();
  if (!(status & SSTATUS_SPP))
    stop_trap("kerneltrap called from user mode");
  if (status & SSTATUS_SIE)
    stop_trap("kerneltrap entered with interrupts enabled");

  if (cause == ((1UL << 63) | 1)) {
    // Supervisor software interrupt: clear the request before returning.
    w_sip(r_sip() & ~2UL);
    kernel_softirq_count++;
  } else if (cause == ((1UL << 63) | 9)) {
    external_interrupt();
  } else {
    kerneltrap_stop();
  }
  // An interrupt does not consume a user ecall: resume at the unchanged PC.
  w_sepc(epc);
  w_sstatus(status);
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
    tf->a0 = syscall_dispatch(tf);
  } else if (cause == ((1UL << 63) | 9)) {
    external_interrupt(); // preserve epc and every user register
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
  tf->kernel_sp = kernel_stack_top();
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
