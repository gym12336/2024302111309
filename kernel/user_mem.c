#include "user_mem.h"
#include "riscv.h"
#include "memlayout.h"

// This lab's user maps use 4 KiB leaves. Kernel identity mappings access RAM PAs.
static uint64
user_page_pa(uint64 *table, uint64 address)
{
  if (!table || address >= MAXVA)
    return 0;
  for (int level = 2; level >= 0; level--) {
    uint64 pte = table[PX(level, address)];
    if (!(pte & PTE_V))
      return 0;
    uint64 pa = PTE2PA(pte);
    if (pa < KERNBASE || pa > PHYSTOP - PGSIZE)
      return 0;
    if (pte & (PTE_R | PTE_W | PTE_X)) {
      if (level != 0 || !(pte & PTE_U) || !(pte & PTE_R))
        return 0;
      return pa;
    }
    if (level == 0)
      return 0;
    table = (uint64 *)pa;
  }
  return 0;
}

int
user_readable(uint64 *table, uint64 address, uint64 length)
{
  if (length == 0)
    return 1; // No memory is read for an empty request.
  if (address >= MAXVA || length > MAXVA - address)
    return 0; // Avoid both an out-of-range address and addition overflow.
  while (length) {
    if (!user_page_pa(table, address))
      return 0;
    uint64 chunk = PGSIZE - (address & (PGSIZE - 1));
    if (chunk > length)
      chunk = length;
    address += chunk;
    length -= chunk;
  }
  return 1;
}

int
user_copyin(uint64 *table, void *destination, uint64 source, uint64 length)
{
  if (!user_readable(table, source, length))
    return -1;
  uint8 *output = destination;
  while (length) {
    uint64 offset = source & (PGSIZE - 1);
    uint64 pa = user_page_pa(table, source);
    uint64 chunk = PGSIZE - offset;
    if (chunk > length)
      chunk = length;
    const uint8 *input = (const uint8 *)(pa + offset);
    for (uint64 i = 0; i < chunk; i++)
      output[i] = input[i];
    output += chunk;
    source += chunk;
    length -= chunk;
  }
  return 0;
}
