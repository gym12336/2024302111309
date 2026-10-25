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
// kfree: accept only an aligned, currently allocated managed page; else -1.
void *kalloc(void);
int kfree(void *page);

#endif
