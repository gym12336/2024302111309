#include "vm_ops.h"
#include "kalloc.h"
extern void vmprintf(const char *, ...);

pte_t *walk(pagetable_t table, uint64 va, int alloc)
{
  if (!table || va >= MAXVA) return 0;
  pte_t *created[2];
  int count = 0;
  for (int level = 2; level > 0; level--) {
    pte_t *pte = &table[PX(level, va)];
    if (*pte & PTE_V) {
      if (*pte & (PTE_R | PTE_W | PTE_X)) goto fail;
      table = (pagetable_t)PTE2PA(*pte);
    } else {
      if (!alloc || !(table = kalloc())) goto fail;
      *pte = PA2PTE(table) | PTE_V;
      created[count++] = pte;
    }
  }
  return &table[PX(0, va)];
fail:
  while (count) {
    pte_t *pte = created[--count];
    void *page = (void *)PTE2PA(*pte);
    *pte = 0;
    kfree(page);
  }
  return 0;
}

static void prune(pagetable_t root, uint64 va)
{
  pagetable_t tables[3];
  pte_t *links[2];
  tables[2] = root;
  for (int l = 2; l > 0; l--) {
    links[l-1] = &tables[l][PX(l, va)];
    pte_t p = *links[l-1];
    if (!(p & PTE_V) || (p & (PTE_R|PTE_W|PTE_X))) return;
    tables[l-1] = (pagetable_t)PTE2PA(p);
  }
  for (int l = 0; l < 2; l++) {
    for (int i = 0; i < 512; i++) if (tables[l][i] & PTE_V) return;
    *links[l] = 0;
    sfence_vma();
    kfree(tables[l]);
  }
}

int mappages(pagetable_t root, uint64 va, uint64 size, uint64 pa, int perm)
{
  if (!size || va % PGSIZE || pa % PGSIZE || va >= MAXVA ||
      size > MAXVA-va || !(perm & (PTE_R|PTE_X)) ||
      ((perm & PTE_W) && !(perm & PTE_R))) return -1;
  uint64 end = PGROUNDUP(va+size), cursor = va;
  for (; cursor < end; cursor += PGSIZE, pa += PGSIZE) {
    pte_t *pte = walk(root, cursor, 1);
    if (!pte || (*pte & PTE_V)) {
      uvmunmap(root, va, (cursor-va)/PGSIZE, 0);
      return -1;
    }
    *pte = PA2PTE(pa) | perm | PTE_V | (1UL<<6) | (1UL<<7);
  }
  sfence_vma();
  return 0;
}

void uvmunmap(pagetable_t root, uint64 va, uint64 pages, int release)
{
  for (uint64 i = 0; i < pages; i++, va += PGSIZE) {
    pte_t *pte = walk(root, va, 0);
    if (pte && (*pte & PTE_V)) {
      uint64 pa = PTE2PA(*pte);
      *pte = 0;
      sfence_vma();
      if (release) kfree((void *)pa);
    }
    prune(root, va);
  }
}

void vmfree(pagetable_t table, int payload)
{
  if (!table) return;
  for (int i = 0; i < 512; i++) {
    pte_t p = table[i];
    if (!(p & PTE_V)) continue;
    table[i] = 0;
    if (!(p & (PTE_R|PTE_W|PTE_X))) vmfree((pagetable_t)PTE2PA(p), payload);
    else if (payload && (p & PTE_U)) kfree((void *)PTE2PA(p));
  }
  kfree(table);
}

static void dump_level(pagetable_t table, int level, uint64 base)
{
  for (int i = 0; i < 512; i++) {
    pte_t p = table[i];
    if (!(p & PTE_V)) continue;
    uint64 va = base | ((uint64)i << PXSHIFT(level));
    uint64 pa = PTE2PA(p);
    char perm[5] = "----";
    if (p & PTE_R) perm[0]='r';
    if (p & PTE_W) perm[1]='w';
    if (p & PTE_X) perm[2]='x';
    if (p & PTE_U) perm[3]='u';
    if (p & (PTE_R|PTE_W|PTE_X))
      vmprintf("LEAF va=0x%lx pa=0x%lx perm=%s\n", va, pa, perm);
    else {
      vmprintf("L%d va=0x%lx pa=0x%lx perm=----\n", level, va, pa);
      if (level) dump_level((pagetable_t)pa, level-1, va);
    }
  }
}
void dump_pagetable(pagetable_t table)
{
  vmprintf("\nDUMP-PAGETABLE begin\n");
  dump_level(table, 2, 0);
  vmprintf("DUMP-PAGETABLE end\n");
}
