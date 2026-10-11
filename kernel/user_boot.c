#include "trapframe.h"
#include "riscv.h"
#include "memlayout.h"
#include "trap.h"
#include "proc.h"

#define PROBE_ENTRY 0x1000UL
#define PROBE_STACK 0x3000UL
#define PTE_A (1UL << 6)
#define PTE_D (1UL << 7)

static uint64 user_root[512] __attribute__((aligned(PGSIZE)));
static uint64 user_low_l1[512] __attribute__((aligned(PGSIZE)));
static uint64 user_low_l0[512] __attribute__((aligned(PGSIZE)));
static uint64 user_high_l1[512] __attribute__((aligned(PGSIZE)));
static uint64 user_high_l0[512] __attribute__((aligned(PGSIZE)));
static uint8 probe_code[PGSIZE] __attribute__((aligned(PGSIZE)));
static uint8 probe_stack[PGSIZE] __attribute__((aligned(PGSIZE)));

extern uint64 boot_trapframe_pa(void);
extern char trampoline[], user_probe_start[], user_probe_end[];
extern void printf(const char *format, ...);

void
user_probe_launch(void)
{
  proc_boot_init();
  uint64 length = (uint64)user_probe_end - (uint64)user_probe_start;
  if (length > PGSIZE) {
    printf("user probe exceeds one page\n");
    for (;;) asm volatile("wfi");
  }
  for (uint64 i = 0; i < length; i++)
    probe_code[i] = user_probe_start[i];

  // Code and stack are the only U-accessible leaves. Page 0 and 0x2000 stay unmapped.
  user_root[PX(2, PROBE_ENTRY)] = PA2PTE(user_low_l1) | PTE_V;
  user_low_l1[PX(1, PROBE_ENTRY)] = PA2PTE(user_low_l0) | PTE_V;
  user_low_l0[PX(0, PROBE_ENTRY)] = PA2PTE(probe_code) | PTE_V | PTE_R | PTE_X | PTE_U | PTE_A;
  user_low_l0[PX(0, PROBE_STACK)] = PA2PTE(probe_stack) | PTE_V | PTE_R | PTE_W | PTE_U | PTE_A | PTE_D;

  user_root[PX(2, TRAMPOLINE)] = PA2PTE(user_high_l1) | PTE_V;
  user_high_l1[PX(1, TRAMPOLINE)] = PA2PTE(user_high_l0) | PTE_V;
  user_high_l0[PX(0, TRAMPOLINE)] = PA2PTE(trampoline) | PTE_V | PTE_R | PTE_X | PTE_A;
  user_high_l0[PX(0, TRAPFRAME)] = PA2PTE(boot_trapframe_pa()) | PTE_V | PTE_R | PTE_W | PTE_A | PTE_D;
  myproc()->pagetable = user_root;

  struct trapframe *tf = (struct trapframe *)TRAPFRAME;
  // Header offsets are compile-checked. Give x1..x31 distinct test values.
  for (uint64 reg = 1; reg <= 31; reg++) {
    uint64 *slot = (uint64 *)((uint8 *)tf + 40 + (reg - 1) * 8);
    *slot = 0x100 + reg;
  }
  tf->epc = PROBE_ENTRY;
  tf->sp = PROBE_STACK + PGSIZE;
  tf->a0 = 123;
  tf->a7 = 999; // Deliberately unsupported; the expected result is -1.
  usertrapret(MAKE_SATP(user_root));
}
