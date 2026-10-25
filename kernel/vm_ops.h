#ifndef VM_H
#define VM_H
#include "types.h"
#include "riscv.h"
pte_t *walk(pagetable_t, uint64, int);
int mappages(pagetable_t, uint64, uint64, uint64, int);
void uvmunmap(pagetable_t, uint64, uint64, int);
void vmfree(pagetable_t, int);
void dump_pagetable(pagetable_t);
#endif
