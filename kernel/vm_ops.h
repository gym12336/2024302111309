#ifndef VM_H
#define VM_H
#include "types.h"
#include "riscv.h"
#define PTE_COW (1L << 8) // writable user page shared read-only until a write

pte_t *walk(pagetable_t, uint64, int);
int mappages(pagetable_t, uint64, uint64, uint64, int);
void uvmunmap(pagetable_t, uint64, uint64, int);
void vmfree(pagetable_t, int);
int uvmcopy(pagetable_t, pagetable_t, uint64);
int cow_alloc(pagetable_t, uint64);
void dump_pagetable(pagetable_t);
#endif
