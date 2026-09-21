#include "types.h"
#include "riscv.h"
#include "memlayout.h"
#include "course_sid.h"

#define UART_THR 0
#define UART_LSR 5
#define UART_LSR_THRE (1 << 5)

#define UART_REG(offset) ((volatile uint8 *)(UART0 + (offset)))
#define LAB1_THROTTLE_PERIOD (16UL + (COURSE_SID % 16UL))

static uint64 transmitted_bytes;

static void
throttle_if_needed(void)
{
  if (transmitted_bytes % LAB1_THROTTLE_PERIOD != 0)
    return;

  for (uint64 i = 0; i < LAB1_THROTTLE_PERIOD; i++)
    asm volatile("nop");
}

void
uartputc_sync(int c)
{
  while ((*UART_REG(UART_LSR) & UART_LSR_THRE) == 0)
    ;

  io_fence();
  *UART_REG(UART_THR) = (uint8)c;
  io_fence();

  transmitted_bytes++;
  throttle_if_needed();
}

void
putchar(int c)
{
  uartputc_sync(c);

#if LAB1_BANNER_PROTOCOL == 1
  uartputc_sync('.');
#elif LAB1_BANNER_PROTOCOL != 0
#error "This lab1 implementation expects banner protocol 0 or 1"
#endif
}
