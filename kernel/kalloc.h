#ifndef KALLOC_H
#define KALLOC_H

#include "types.h"

// Physical addresses use the kernel's RAM identity mapping when dereferenced.
struct kalloc_stats {
  uint64 first_pa;    // Inclusive, page-aligned managed range start.
  uint64 limit_pa;    // Exclusive; the highest DELTA pages are excluded.
  uint64 total_pages;
  uint64 free_pages;
};

// Initialize once, before other users access the allocator. Return 0 or -1.
// All runtime user pages and page tables come from this same allocator.
int kinit(void);
int kalloc_get_stats(struct kalloc_stats *out);

// kalloc: return one zeroed page, or 0 on exhaustion/uninitialized allocator.
// kfree: release one reference; reject an invalid address and panic on underflow.
void *kalloc(void);
int kfree(void *page);
void kref_inc(uint64 pa);
uint16 kref_get(uint64 pa);
uint64 kshared_count(void);
uint64 kcow_copy_count(void);
int kref_selftest(void);

// Resolve a validated COW PTE. Return 1 for a copy, 0 for reuse, -1 on OOM.
int kcow_split(uint64 *pte);

#endif
