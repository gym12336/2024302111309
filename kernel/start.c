#include "types.h"
#include "riscv.h"

extern void main(void);

void
start(void)
{
  w_tp(r_mhartid());
  // Tell mret to lower the privilege level from M-mode to S-mode.
  uint64 status = r_mstatus();
  status &= ~MSTATUS_MPP_MASK;
  status |= MSTATUS_MPP_S;
  w_mstatus(status);

  // Tell mret to continue at main(), with address translation disabled.
  w_mepc((uint64)main);
  w_satp(0);

  // Let S-mode handle the exceptions and interrupts that can be delegated.
  w_medeleg(0xffff);
  w_mideleg(0xffff);

  // Sstc: supervisor timer uses CSR access; CLINT MMIO is unnecessary.
  w_menvcfg(r_menvcfg() | MENVCFG_STCE);
  w_mcounteren(7);
  w_stimecmp(~0UL);

  // Allow S-mode to read, write, and execute across the physical address space.
  w_pmpaddr0(0x3fffffffffffffull);
  w_pmpcfg0(0xf);

  asm volatile("mret");

  // mret transfers control to main(), so this is only a defensive fallback.
  for (;;)
    asm volatile("wfi");
}
