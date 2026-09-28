#include "types.h"
#include "riscv.h"
#include "memlayout.h"

// A small boot-only Sv39 map. It keeps the Lab1 physical addresses working
// while making the trampoline and trapframe's high virtual addresses usable.
static uint64 root[512] __attribute__((aligned(PGSIZE)));
static uint64 top_l1[512] __attribute__((aligned(PGSIZE)));
static uint64 top_l0[512] __attribute__((aligned(PGSIZE)));
static uint8 boot_trapframe[PGSIZE] __attribute__((aligned(PGSIZE)));

extern char trampoline[];

#define PTE_A (1L << 6)
#define PTE_D (1L << 7)

static void
stop_boot(void)
{
  for (;;)
    asm volatile("wfi");
}

void
boot_vm_init(void)
{
  if (((uint64)trampoline & (PGSIZE - 1)) != 0)
    stop_boot();

  // Level-2 leaves identity-map the device region and kernel RAM.
  // These broad boot mappings will be narrowed when process page tables arrive.
  root[PX(2, UART0)] = PA2PTE(0) | PTE_V | PTE_R | PTE_W | PTE_X | PTE_A | PTE_D;
  root[PX(2, KERNBASE)] = PA2PTE(KERNBASE) | PTE_V | PTE_R | PTE_W | PTE_X | PTE_A | PTE_D;

  // Two level-0 leaves back the fixed high virtual addresses used by uservec.
  root[PX(2, TRAMPOLINE)] = PA2PTE(top_l1) | PTE_V;
  top_l1[PX(1, TRAMPOLINE)] = PA2PTE(top_l0) | PTE_V;
  top_l0[PX(0, TRAMPOLINE)] = PA2PTE(trampoline) | PTE_V | PTE_R | PTE_X | PTE_A;
  top_l0[PX(0, TRAPFRAME)] = PA2PTE(boot_trapframe) | PTE_V | PTE_R | PTE_W | PTE_A | PTE_D;

  w_satp(MAKE_SATP(root));
  asm volatile("sfence.vma zero, zero" ::: "memory");

  // Exercise both aliases now, before any user process depends on them.
  if (*(volatile uint32 *)TRAMPOLINE != *(volatile uint32 *)trampoline)
    stop_boot();
  *(volatile uint64 *)TRAPFRAME = 0x4c414232UL; // "LAB2"
  if (*(volatile uint64 *)TRAPFRAME != *(volatile uint64 *)boot_trapframe)
    stop_boot();
  *(volatile uint64 *)TRAPFRAME = 0;
}
