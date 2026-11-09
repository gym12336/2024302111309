#include "types.h"
#include "riscv.h"
#include "memlayout.h"
#include "course_sid.h"
#include "uart.h"
#include "console.h"
#include "user_mem.h"
#include "proc.h"

#if LAB2_BUF_SIZE <= 0 || (LAB2_BUF_SIZE & (LAB2_BUF_SIZE - 1)) != 0
#error "Input ring capacity must be a positive power of two"
#endif
#if LAB2_BUF_SEMANTICS != 0 && LAB2_BUF_SEMANTICS != 1
#error "Input semantics must be line (0) or stream (1)"
#endif

static struct {
  struct spinlock lock;
  uint8 buf[LAB2_BUF_SIZE];
  uint64 r; // next byte to consume
  uint64 w; // end of committed (readable) bytes
  uint64 e; // end of all stored bytes, including an unfinished line
  uint64 dropped;
} input;

void
console_input(int c)
{
  if (c < 0 || c > 255)
    return;
  acquire(&input.lock);
  if (input.e - input.r == LAB2_BUF_SIZE) {
    input.dropped++;
    release(&input.lock);
    return; // keep existing data; neither store nor echo a dropped byte
  }
  input.buf[input.e % LAB2_BUF_SIZE] = (uint8)c;
  input.e++;
#if LAB2_BUF_SEMANTICS == 1
  input.w = input.e;
#else
  // A full partial line must be readable to let a consumer free capacity.
  if (c == '\n' || input.e - input.r == LAB2_BUF_SIZE)
    input.w = input.e;
#endif
  uartputc_sync(c);
  wakeup(&input.r);
  release(&input.lock);
}

int
console_getc(void)
{
  acquire(&input.lock);
  int c = -1;
  if (input.r != input.w) {
    c = input.buf[input.r % LAB2_BUF_SIZE];
    input.r++;
  }
  release(&input.lock);
  return c;
}

int
console_read(uint64 *pagetable, uint64 destination, uint64 length)
{
  // Reject the entire destination before consuming any queued input.
  if (!user_writable(pagetable, destination, length))
    return -1;
  if (length == 0)
    return 0;
  acquire(&input.lock);
  uint64 done = 0;
  while (done < length) {
    if (input.r == input.w) {
      if (done)
        break; // Return available bytes instead of waiting to fill the request.
      if (proc_killed()) { release(&input.lock); return -1; }
      sleep(&input.r, &input.lock);
      continue;
    }
    int c = input.buf[input.r++ % LAB2_BUF_SIZE];
    uint8 byte = (uint8)c;
    if (user_copyout(pagetable, destination + done, &byte, 1) < 0) {
      release(&input.lock);
      return -1; // Current single-task mappings cannot change during the copy.
    }
    done++;
#if LAB2_BUF_SEMANTICS == 0
    if (c == '\n')
      break;
#endif
  }
  release(&input.lock);
  return (int)done;
}

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
  initlock(&input.lock, "console");
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
    console_input(c);
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
