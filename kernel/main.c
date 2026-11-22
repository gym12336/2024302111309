#include "course_sid.h"
#include "trap.h"
#include "riscv.h"
#include "uart.h"
#include "plic.h"
#include "proc.h"
#include "kalloc.h"

extern void printf(const char *format, ...);
extern void vmprintf(const char *format, ...);
extern void boot_vm_init(void);
extern void boot_vm_hart_init(void);
extern void user_probe_launch(void) __attribute__((noreturn));
static int started;

void
main(void)
{
  if (r_tp() != 0) {
    while (!__atomic_load_n(&started, __ATOMIC_ACQUIRE))
      asm volatile("nop" ::: "memory");
    boot_vm_hart_init();
    trap_init();
    plic_init();
    w_stimecmp(r_time() + 100000);
    w_sie(r_sie() | SIE_SEIE | SIE_STIE);
    scheduler();
  }
  boot_vm_init();
  proc_boot_init();
  trap_init();
  uart_init();
  plic_init();
  w_stimecmp(r_time() + 100000);
  w_sie(r_sie() | SIE_SEIE | SIE_STIE);

  printf("OSLAB1 sid=%lu mod97=0x%lx\n",
         (unsigned long)COURSE_SID,
         (unsigned long)(COURSE_SID % 97UL));

  printf("SELFTEST zero=%d neg=%d max=%d empty=[%s]\n",
         0, -123, 2147483647, "");

  printf("SELFTEST long=%s\n",
         "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
         "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789");

  if (kref_selftest() < 0) panic("kref selftest");
  vmprintf("LAB5 kref_selftest PASS\n");

#ifdef LAB2_BOOT_PROBE
  intr_on();
  user_probe_launch();
#else
  proc_shell_init();
  // Publish global tables, locks, UART and the initial user process together.
  __atomic_store_n(&started, 1, __ATOMIC_RELEASE);
  scheduler();
#endif
}
