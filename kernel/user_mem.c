#include "user_mem.h"
#include "riscv.h"
#include "memlayout.h"

// This lab's user maps use 4 KiB leaves. Kernel identity mappings access RAM PAs.
static uint64
user_page_pa(uint64 *table, uint64 address, int writing)
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
      if (writing && !(pte & PTE_W))
        return 0;
      return pa;
    }
    if (level == 0)
      return 0;
    table = (uint64 *)pa;
  }
  return 0;
}

static int
user_accessible(uint64 *table, uint64 address, uint64 length, int writing)
{
  if (length == 0)
    return 1; // An empty request accesses no memory.
  if (address >= MAXVA || length > MAXVA - address)
    return 0; // Avoid both an out-of-range address and addition overflow.
  while (length) {
    if (!user_page_pa(table, address, writing))
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
user_readable(uint64 *table, uint64 address, uint64 length)
{
  return user_accessible(table, address, length, 0);
}

int
user_writable(uint64 *table, uint64 address, uint64 length)
{
  return user_accessible(table, address, length, 1);
}

int
user_copyin(uint64 *table, void *destination, uint64 source, uint64 length)
{
  if (!user_readable(table, source, length))
    return -1;
  uint8 *output = destination;
  while (length) {
    uint64 offset = source & (PGSIZE - 1);
    uint64 pa = user_page_pa(table, source, 0);
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

int
user_copyout(uint64 *table, uint64 destination, const void *source, uint64 length)
{
  // Check the entire range before storing, so a bad suffix writes no prefix.
  if (!user_writable(table, destination, length))
    return -1;
  const uint8 *input = source;
  while (length) {
    uint64 offset = destination & (PGSIZE - 1);
    uint64 pa = user_page_pa(table, destination, 1);
    uint64 chunk = PGSIZE - offset;
    if (chunk > length)
      chunk = length;
    uint8 *output = (uint8 *)(pa + offset);
    for (uint64 i = 0; i < chunk; i++)
      output[i] = input[i];
    input += chunk;
    destination += chunk;
    length -= chunk;
  }
  return 0;
}
