#include "types.h"
#include "riscv.h"
#include "memlayout.h"
#include "vm_ops.h"
#include "kalloc.h"

// Kernel Sv39 map: device MMIO, all RAM and shared high trampoline/frame aliases.
static uint64 root[512] __attribute__((aligned(PGSIZE)));
static uint64 top_l1[512] __attribute__((aligned(PGSIZE)));
static uint64 top_l0[512] __attribute__((aligned(PGSIZE)));
static uint8 boot_trapframe[PGSIZE] __attribute__((aligned(PGSIZE)));

extern char trampoline[];

// The first user map must refer to the same physical frame as the kernel map.
uint64
boot_trapframe_pa(void)
{
  return (uint64)boot_trapframe;
}

void
boot_trapframe_select(uint64 physical_address)
{
  // Select the running process's frame in the kernel's fixed high alias.
  top_l0[PX(0, TRAPFRAME)] = PA2PTE(physical_address) | PTE_V | PTE_R | PTE_W |
                           (1UL << 6) | (1UL << 7);
  asm volatile("sfence.vma zero, zero" ::: "memory");
}

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

  if (kinit() < 0 ||
      mappages(root, UART0, PGSIZE, UART0, PTE_R|PTE_W) < 0 ||
      mappages(root, PLIC, 0x400000, PLIC, PTE_R|PTE_W) < 0 ||
      mappages(root, KERNBASE, PHYSTOP-KERNBASE, KERNBASE, PTE_R|PTE_W|PTE_X) < 0)
    stop_boot();

  // Two level-0 leaves back the fixed high virtual addresses used by uservec.
  root[PX(2, TRAMPOLINE)] = PA2PTE(top_l1) | PTE_V;
  top_l1[PX(1, TRAMPOLINE)] = PA2PTE(top_l0) | PTE_V;
  top_l0[PX(0, TRAMPOLINE)] = PA2PTE(trampoline) | PTE_V | PTE_R | PTE_X | PTE_A;
  top_l0[PX(0, TRAPFRAME)] = PA2PTE(boot_trapframe) | PTE_V | PTE_R | PTE_W | PTE_A | PTE_D;

  sfence_vma();
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
