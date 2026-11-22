#include "kalloc.h"
#include "riscv.h"
#include "memlayout.h"
#include "course_sid.h"
#include "spinlock.h"
#include "vm_ops.h"

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
  uint16 refcnt[RAM_PAGES];
  uint64 shared_pages;
  uint64 cow_copies;
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

  // Boot populates the free bitmap directly; free pages start at refcount 0.
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

static int
managed_page(uint64 pa)
{
  return kmem.initialized && pa % PGSIZE == 0 &&
         pa >= kmem.first_pa && pa < kmem.limit_pa;
}

// Reserve a page with one reference. The caller supplies its contents.
static uint64
reserve_page(void)
{
  if (!kmem.free_pages) return 0;
  while (!kmem.free_bitmap[kmem.search_word]) kmem.search_word--;
  uint64 bits = kmem.free_bitmap[kmem.search_word];
  int bit = 63;
  while (!(bits & (1UL << bit))) bit--;
  kmem.free_bitmap[kmem.search_word] &= ~(1UL << bit);
  kmem.free_pages--;
  uint64 index = kmem.search_word * BITS_PER_WORD + bit;
  kmem.refcnt[index] = 1;
  return KERNBASE + index * PGSIZE;
}

void *kalloc(void)
{
  if (!kmem.initialized) return 0;
  acquire(&kmem.lock);
  uint64 pa = reserve_page();
  // The cleared bitmap bit reserves this page exclusively. Clearing its bytes
  // after unlocking lets another hart allocate a different page in parallel.
  release(&kmem.lock);
  if (pa)
    for (uint64 i = 0; i < PGSIZE; i++) ((uint8 *)pa)[i] = 0;
  return (void *)pa;
}

static void
drop_ref(uint64 pa)
{
  uint64 index = (pa - KERNBASE) / PGSIZE;
  if (!kmem.refcnt[index]) panic("kfree: refcnt underflow");
  uint16 refs = --kmem.refcnt[index];
  if (refs == 1) kmem.shared_pages--;
  if (refs) return;

  // Publish the free bit only after poisoning the last reference's data.
  for (uint64 i = 0; i < PGSIZE; i++) ((uint8 *)pa)[i] = 0x5a;
  uint64 word = index / BITS_PER_WORD;
  kmem.free_bitmap[word] |= 1UL << (index % BITS_PER_WORD);
  kmem.free_pages++;
  if (word > kmem.search_word) kmem.search_word = word;
}

int kfree(void *page)
{
  uint64 pa = (uint64)page;
  if (!managed_page(pa)) return -1;
  acquire(&kmem.lock);
  drop_ref(pa);
  release(&kmem.lock);
  return 0;
}

void
kref_inc(uint64 pa)
{
  if (!managed_page(pa)) panic("kref_inc: invalid page");
  uint64 index = (pa - KERNBASE) / PGSIZE;
  acquire(&kmem.lock);
  uint16 refs = kmem.refcnt[index];
  if (!refs || refs == 0xffff) panic("kref_inc: invalid refcnt");
  if (refs == 1) kmem.shared_pages++;
  kmem.refcnt[index] = refs + 1;
  release(&kmem.lock);
}

uint16
kref_get(uint64 pa)
{
  if (!managed_page(pa)) return 0;
  acquire(&kmem.lock);
  uint16 count = kmem.refcnt[(pa - KERNBASE) / PGSIZE];
  release(&kmem.lock);
  return count;
}

uint64
kshared_count(void)
{
  acquire(&kmem.lock);
  uint64 count = kmem.shared_pages;
  release(&kmem.lock);
  return count;
}

uint64
kcow_copy_count(void)
{
  acquire(&kmem.lock);
  uint64 count = kmem.cow_copies;
  release(&kmem.lock);
  return count;
}

int
kcow_split(uint64 *pte)
{
  uint64 old_pa = PTE2PA(*pte);
  if (!managed_page(old_pa)) return -1;
  uint64 index = (old_pa - KERNBASE) / PGSIZE;
  uint64 flags = (PTE_FLAGS(*pte) | PTE_W) & ~PTE_COW;

  // Keep the refcount decision, page copy and reference drop together.
  // A second hart resolving the same shared PA sees the updated count.
  acquire(&kmem.lock);
  uint16 refs = kmem.refcnt[index];
  if (!refs) panic("kcow_split: missing reference");
  if (refs == 1) {
    *pte = PA2PTE(old_pa) | flags;
    sfence_vma();
    release(&kmem.lock);
    return 0;
  }
  uint64 new_pa = reserve_page();
  if (!new_pa) {
    release(&kmem.lock);
    return -1;
  }
  const uint64 *source = (const uint64 *)old_pa;
  uint64 *destination = (uint64 *)new_pa;
  for (uint64 i = 0; i < PGSIZE / sizeof(*destination); i++)
    destination[i] = source[i];
  *pte = PA2PTE(new_pa) | flags;
  sfence_vma();
  drop_ref(old_pa);
  kmem.cow_copies++;
  release(&kmem.lock);
  return 1;
}

int
kref_selftest(void)
{
  struct kalloc_stats before, after;
  if (kalloc_get_stats(&before) < 0 || kshared_count() != 0) return -1;
  uint8 *page = kalloc();
  if (!page || kref_get((uint64)page) != 1) return -1;
  page[0] = 0xc3;
  kref_inc((uint64)page);
  kref_inc((uint64)page);
  if (kref_get((uint64)page) != 3 || kshared_count() != 1) return -1;
  if (kfree(page) < 0 || kref_get((uint64)page) != 2 || page[0] != 0xc3 ||
      kshared_count() != 1) return -1;
  if (kfree(page) < 0 || kref_get((uint64)page) != 1 || page[0] != 0xc3 ||
      kshared_count() != 0) return -1;
  return kfree(page) == 0 && kref_get((uint64)page) == 0 &&
         page[0] == 0x5a && kalloc_get_stats(&after) == 0 &&
         before.free_pages == after.free_pages ? 0 : -1;
}
