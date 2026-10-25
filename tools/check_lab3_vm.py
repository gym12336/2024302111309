#!/usr/bin/env python3
"""Run allocator and rollback contracts on real RISC-V, in an isolated kernel."""
import pathlib
import tempfile
import check_kalloc_init as harness

EXTRA = r'''
  struct kalloc_stats before, after;
  require(kalloc_get_stats(&before) == 0);
  void *a = kalloc(), *b = kalloc();
  require(a && b && (uint64)a > (uint64)b && (uint64)a % PGSIZE == 0);
  for (int i=0; i<PGSIZE; i++) require(((uint8 *)a)[i] == 0);
  ((uint8 *)a)[0] = 99;
  require(kfree(a) == 0 && kfree(a) == -1);
  require(kalloc() == a && ((uint8 *)a)[0] == 0);
  require(kfree(a) == 0 && kfree(b) == 0);
  require(kfree((void *)KERNBASE) == -1 && kfree((void *)1) == -1);
  emit("ALLOC PASS: descending, alignment, zero, reuse, invalid/double free\n");
  pagetable_t table = kalloc();
  require(table != 0);
  require(walk(table, MAXVA, 1) == 0 && walk(table, 0, 0) == 0);
  require(mappages(table, 0, PGSIZE, KERNBASE, PTE_R|PTE_U) == 0);
  pte_t original = *walk(table, 0, 0);
  require(mappages(table, 0, PGSIZE, KERNBASE, PTE_R|PTE_W) == -1);
  require(*walk(table, 0, 0) == original);
  uvmunmap(table, 0, 1, 0);
  require(walk(table, 0, 0) == 0);
  require(kalloc_get_stats(&before) == 0);
  uint64 held_count = 0;
  void *page;
  while ((page = kalloc())) held[held_count++] = page;
  require(held_count == before.free_pages && kalloc() == 0);
  require(kfree(held[--held_count]) == 0);
  // One intermediate page succeeds, next fails; walk must undo the first.
  require(walk(table, 0, 1) == 0);
  require(kalloc_get_stats(&after) == 0 && after.free_pages == 1);
  require(kfree(held[--held_count]) == 0);
  // 512 mappings succeed with two table pages, then next L0 allocation fails.
  require(mappages(table, 0, 513UL*PGSIZE, KERNBASE, PTE_R|PTE_W) == -1);
  require(kalloc_get_stats(&after) == 0 && after.free_pages == 2);
  for (int i=0; i<512; i++) require(table[i] == 0);
  while (held_count) require(kfree(held[--held_count]) == 0);
  vmfree(table, 0);
  require(kalloc_get_stats(&after) == 0 && after.free_pages == info.free_pages);
  emit("ROLLBACK PASS: walk OOM, mapping page 513 OOM, empty branches reclaimed, counts conserved\n");
'''


def main():
    root = pathlib.Path(__file__).resolve().parents[1]
    # Keep the original initialization assertions, then add dynamic contracts.
    harness.PROBE = harness.PROBE.replace('#include "kalloc.c"',
        '#include "kalloc.c"\n#include "vm.c"\n'
        'void vmprintf(const char *format, ...) { (void)format; }\n'
        'static void *held[32768];')
    harness.PROBE = harness.PROBE.replace('  emit("KINIT PASS:', EXTRA+'\n  emit("KINIT PASS:')
    with tempfile.TemporaryDirectory(prefix='lab3-vm-') as folder:
        harness.run_case(root, pathlib.Path(folder), 5001)
    print('PASS: isolated RISC-V allocator and page-table rollback tests')


if __name__ == '__main__':
    main()
