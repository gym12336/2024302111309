#include "user_mem.h"
#include "riscv.h"
#include "memlayout.h"
#include "vm_ops.h"

// This lab's user maps use 4 KiB leaves. Kernel identity mappings access RAM PAs.
static pte_t *
user_page(uint64 *table, uint64 address)
{
  if (!table || address >= MAXVA)
    return 0;
  for (int level = 2; level >= 0; level--) {
    pte_t *entry = &table[PX(level, address)];
    uint64 pte = *entry;
    if (!(pte & PTE_V))
      return 0;
    uint64 pa = PTE2PA(pte);
    if (pa < KERNBASE || pa > PHYSTOP - PGSIZE)
      return 0;
    if (pte & (PTE_R | PTE_W | PTE_X)) {
      if (level != 0 || !(pte & PTE_U) || !(pte & PTE_R))
        return 0;
      return entry;
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
  uint64 first = PGROUNDDOWN(address), last = PGROUNDDOWN(address + length - 1);
  int needs_cow = 0;
  for (uint64 va = first; va <= last; va += PGSIZE) {
    pte_t *pte = user_page(table, va);
    if (!pte) return 0;
    if (writing && !(*pte & PTE_W)) {
      if (!(*pte & PTE_COW)) return 0;
      needs_cow = 1;
    }
  }
  // Check all permissions before splitting a page or consuming console input.
  if (needs_cow) {
    for (uint64 va = first; va <= last; va += PGSIZE) {
      pte_t *pte = user_page(table, va);
      if (!(*pte & PTE_W) && cow_alloc(table, va) < 0)
        return 0;
    }
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
    uint64 pa = PTE2PA(*user_page(table, source));
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
    uint64 pa = PTE2PA(*user_page(table, destination));
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
