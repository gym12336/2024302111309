#include "kalloc.h"
#include "riscv.h"
#include "memlayout.h"
#include "course_sid.h"
#include "spinlock.h"

#define RAM_PAGES ((PHYSTOP - KERNBASE) / PGSIZE)
#define BITS_PER_WORD 64UL
#define BITMAP_WORDS ((RAM_PAGES + BITS_PER_WORD - 1) / BITS_PER_WORD)

_Static_assert((PHYSTOP - KERNBASE) % PGSIZE == 0,
               "RAM must contain whole pages");
_Static_assert(LAB3_MEMCAP_DELTA >= 0 && LAB3_MEMCAP_DELTA < RAM_PAGES,
               "reserved page quota must fit in RAM");
_Static_assert(LAB3_ALLOC_ORDER == 1,
               "this student's allocator uses descending allocation");

extern char kernel_end[];

static struct {
  struct spinlock lock;
  // One bit per physical RAM page: 1=free, 0=unavailable or allocated.
  uint64 free_bitmap[BITMAP_WORDS];
  uint64 first_pa;
  uint64 limit_pa;
  uint64 total_pages;
  uint64 free_pages;
  uint64 search_word; // Descending allocation starts at the highest candidate word.
  int initialized;
} kmem;

int
kinit(void)
{
  // Hart 0 alone initializes RAM before the boot publication barrier.
  // A repeated call must never mark already allocated pages free again.
  if (kmem.initialized)
    return -1;
  uint64 image_end = (uint64)kernel_end;
  uint64 limit = PHYSTOP - (uint64)LAB3_MEMCAP_DELTA * PGSIZE;
  if (image_end < KERNBASE || image_end > limit)
    return -1;
  uint64 first = PGROUNDUP(image_end);
  if (first > limit)
    return -1;

  initlock(&kmem.lock, "kmem");

  for (uint64 i = 0; i < BITMAP_WORDS; i++)
    kmem.free_bitmap[i] = 0;
  for (uint64 pa = first; pa < limit; pa += PGSIZE) {
    uint64 page = (pa - KERNBASE) / PGSIZE;
    kmem.free_bitmap[page / BITS_PER_WORD] |=
        1UL << (page % BITS_PER_WORD);
  }

  kmem.first_pa = first;
  kmem.limit_pa = limit;
  kmem.total_pages = (limit - first) / PGSIZE;
  kmem.free_pages = kmem.total_pages;
  kmem.search_word = kmem.total_pages ?
      ((limit - PGSIZE - KERNBASE) / PGSIZE) / BITS_PER_WORD : 0;
  kmem.initialized = 1;
  return 0;
}

int
kalloc_get_stats(struct kalloc_stats *out)
{
  if (!kmem.initialized || !out)
    return -1;
  acquire(&kmem.lock);
  out->first_pa = kmem.first_pa;
  out->limit_pa = kmem.limit_pa;
  out->total_pages = kmem.total_pages;
  out->free_pages = kmem.free_pages;
  release(&kmem.lock);
  return 0;
}

void *kalloc(void)
{
  if (!kmem.initialized) return 0;
  acquire(&kmem.lock);
  if (!kmem.free_pages) { release(&kmem.lock); return 0; }
  while (!kmem.free_bitmap[kmem.search_word]) kmem.search_word--;
  uint64 bits = kmem.free_bitmap[kmem.search_word];
  int bit = 63;
  while (!(bits & (1UL << bit))) bit--;
  kmem.free_bitmap[kmem.search_word] &= ~(1UL << bit);
  kmem.free_pages--;
  uint64 pa = KERNBASE + (kmem.search_word * 64 + bit) * PGSIZE;
  // The cleared bitmap bit reserves this page exclusively. Clearing its bytes
  // after unlocking lets another hart allocate a different page in parallel.
  release(&kmem.lock);
  for (uint64 i = 0; i < PGSIZE; i++) ((uint8 *)pa)[i] = 0;
  return (void *)pa;
}

int kfree(void *page)
{
  uint64 pa = (uint64)page;
  if (!kmem.initialized || pa % PGSIZE || pa < kmem.first_pa || pa >= kmem.limit_pa)
    return -1;
  uint64 index = (pa - KERNBASE) / PGSIZE, word = index / 64;
  uint64 mask = 1UL << (index % 64);
  acquire(&kmem.lock);
  if (kmem.free_bitmap[word] & mask) { release(&kmem.lock); return -1; }
  // Fill before publishing the free bit, while duplicate frees are excluded.
  for (uint64 i = 0; i < PGSIZE; i++) ((uint8 *)page)[i] = 0xA5;
  kmem.free_bitmap[word] |= mask;
  kmem.free_pages++;
  if (word > kmem.search_word) kmem.search_word = word;
  release(&kmem.lock);
  return 0;
}
