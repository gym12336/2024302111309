#include "types.h"
#include "riscv.h"
#include "memlayout.h"
#include "plic.h"

void
plic_init(void)
{
  // Global UART priority is initialized once. Each hart sets its own context;
  // only hart0 services UART RX, while all harts receive their local timer.
  if (r_tp() == 0)
    *(volatile uint32 *)(PLIC_PRIORITY + UART0_IRQ * 4) = 1;
  *(volatile uint32 *)PLIC_SENABLE(r_tp()) = r_tp() == 0 ? 1U << UART0_IRQ : 0;
  *(volatile uint32 *)PLIC_SPRIORITY(r_tp()) = 0;
  io_fence();
}

int
plic_claim(void)
{
  io_fence();
  int irq = *(volatile uint32 *)PLIC_SCLAIM(r_tp());
  io_fence();
  return irq;
}

void
plic_complete(int irq)
{
  io_fence();
  *(volatile uint32 *)PLIC_SCLAIM(r_tp()) = irq;
  io_fence();
}
