#include "types.h"
#include "riscv.h"
#include "memlayout.h"
#include "course_sid.h"
#include "uart.h"

#define UART_RHR 0
#define UART_THR 0
#define UART_IER 1
#define UART_FCR 2
#define UART_LCR 3
#define UART_LSR 5
#define UART_LSR_DR (1 << 0)
#define UART_LSR_THRE (1 << 5)

#define UART_REG(offset) ((volatile uint8 *)(UART0 + (offset)))
#define LAB1_THROTTLE_PERIOD (16UL + (COURSE_SID % 16UL))

static uint64 transmitted_bytes;
static volatile uint64 uart_rx_count;
static volatile uint64 uart_irq_count;

void
uart_init(void)
{
  // Clear DLAB before disabling interrupts: offset 1 must mean IER.
  *UART_REG(UART_LCR) = 3;
  *UART_REG(UART_IER) = 0;
  *UART_REG(UART_LCR) = 0x80;
  *UART_REG(0) = 3; // divisor low byte
  *UART_REG(1) = 0; // divisor high byte
  *UART_REG(UART_LCR) = 3; // 8 data bits, no parity, one stop bit
  *UART_REG(UART_FCR) = 7; // enable FIFO, clear RX/TX, RX threshold one byte
  *UART_REG(UART_IER) = 1; // receive only; synchronous output needs no TX IRQ
  io_fence();
}

int
uartgetc(void)
{
  io_fence();
  if ((*UART_REG(UART_LSR) & UART_LSR_DR) == 0)
    return -1;
  int c = *UART_REG(UART_RHR);
  io_fence();
  return c;
}

void
uartintr(void)
{
  uart_irq_count++;
  int c;
  while ((c = uartgetc()) != -1) {
    // Stage-three first increment: raw echo. The input ring follows next.
    uartputc_sync(c);
    uart_rx_count++;
  }
}

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
