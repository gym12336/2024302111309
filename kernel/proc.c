#include "proc.h"
#include "riscv.h"
#include "memlayout.h"
#include "trapframe.h"
#include "trap.h"
#include "user_mem.h"
#include "vm_ops.h"
#include "kalloc.h"
#include "course_sid.h"

#define PROCESS_SLOTS 4
extern char kernel_end[], trampoline[], _uprog_table[];
extern void boot_trapframe_select(uint64);
extern void proc_exit_idle(void) __attribute__((noreturn));
extern void printf(const char *, ...);

struct image_meta { const char *name; uint64 entry; uint64 memory; uint64 data; };
#include "user_meta.h"

static struct proc boot_process;
static struct proc processes[PROCESS_SLOTS];
static struct proc *current;

static uint64 next_pid;
static int managed;
static struct proc *deferred;
static void release_process(struct proc *p);
void proc_reap_deferred(void)
{
  if (deferred) { struct proc *p = deferred; deferred = 0; release_process(p); }
}

static void clear(void *address, uint64 length)
{
  uint8 *bytes = address;
  for (uint64 i = 0; i < length; i++) bytes[i] = 0;
}

static void copy(void *destination, const void *source, uint64 length)
{
  uint8 *out = destination;
  const uint8 *in = source;
  for (uint64 i = 0; i < length; i++) out[i] = in[i];
}

static int same_name(const char *left, const char *right)
{
  while (*left && *left == *right) { left++; right++; }
  return *left == *right;
}

static const struct image_meta *find_image(const char *name, uint64 *start, uint64 *size)
{
  uint64 cursor = (uint64)_uprog_table;
  while (cursor + 16 <= (uint64)kernel_end) {
    uint64 first = ((uint64 *)cursor)[0];
    uint64 last = ((uint64 *)cursor)[1];
    if (!first) return 0;
    if (last < first || last > (uint64)kernel_end) return 0;
    const char *record_name = (const char *)(cursor + 16);
    if (same_name(record_name, name)) {
      for (uint64 i = 0; i < sizeof(image_metadata) / sizeof(image_metadata[0]); i++) {
        const struct image_meta *meta = &image_metadata[i];
        if (same_name(meta->name, name)) {
          *start = first; *size = last - first;
          return meta;
        }
      }
      return 0;
    }
    // Gift table records are interleaved with their image bytes.
    cursor = (last + 7) & ~7UL;
  }
  return 0;
}

static pagetable_t new_table(struct proc *p)
{
  pagetable_t table = kalloc();
  if (!table) return 0;
  if (mappages(table, TRAMPOLINE, PGSIZE, (uint64)trampoline, PTE_R|PTE_X) < 0 ||
      mappages(table, TRAPFRAME, PGSIZE, (uint64)p->frame, PTE_R|PTE_W) < 0) {
    vmfree(table, 1); return 0;
  }
  return table;
}

static void release_process(struct proc *p)
{
  vmfree(p->pagetable, 1);
  if (p->frame) kfree(p->frame);
  if (p->kernel_stack) kfree((void *)(p->kernel_stack-PGSIZE));
  clear(p, sizeof(*p));
}

static struct proc *allocate_process(void)
{
  for (int i = 0; i < PROCESS_SLOTS; i++) {
    struct proc *p = &processes[i];
    if (p->state != PROC_UNUSED) continue;
    clear(p, sizeof(*p));
    p->frame = kalloc();
    void *stack = kalloc();
    p->kernel_stack = stack ? (uint64)stack+PGSIZE : 0;
    if (!p->frame || !stack || !(p->pagetable = new_table(p))) {
      release_process(p); return 0;
    }
    p->pid = next_pid++;
    p->state = PROC_RUNNABLE;
    return p;
  }
  return 0;
}

static int add_page(pagetable_t table, uint64 va, int flags)
{
  void *page = kalloc();
  if (!page) return -1;
  if (mappages(table, va, PGSIZE, (uint64)page, flags|PTE_U) < 0) {
    kfree(page); return -1;
  }
  return 0;
}

static int load_image(struct proc *p, const char *name)
{
  uint64 start, size;
  const struct image_meta *meta = find_image(name, &start, &size);
  if (!meta || !meta->memory || size > meta->memory || meta->entry >= size ||
      meta->memory > TRAPFRAME-(LAB3_GUARD_PAGES+2)*PGSIZE ||
      meta->data % PGSIZE || meta->data > PGROUNDUP(meta->memory))
    return -1;
  pagetable_t table = new_table(p);
  if (!table) return -1;
  uint64 guard = PGROUNDUP(meta->memory), top = guard+(LAB3_GUARD_PAGES+2)*PGSIZE;
  for (uint64 va = 0; va < top; va += PGSIZE) {
    if (va >= guard && va < guard+LAB3_GUARD_PAGES*PGSIZE) continue;
    int flags = va < meta->data ? PTE_R|PTE_X : PTE_R|PTE_W;
    if (add_page(table, va, flags) < 0) { vmfree(table, 1); return -1; }
    if (va < size) {
      uint64 count = size-va;
      if (count > PGSIZE) count = PGSIZE;
      copy((void *)PTE2PA(*walk(table, va, 0)), (void *)(start+va), count);
    }
  }
  pagetable_t old = p->pagetable;
  p->pagetable = table;
  p->image_size = meta->memory;
  p->heap_base = p->sz = top;
  p->guard = guard;
  clear(p->frame, sizeof(*p->frame));
  p->frame->epc = meta->entry;
  p->frame->sp = top;
  vmfree(old, 1);
  return 0;
}

uint64 proc_sbrk(int n)
{
  struct proc *p = myproc();
  uint64 old = p->sz, next;
  if (n >= 0) {
    if ((uint64)n > TRAPFRAME-old) return (uint64)-1;
    next = old+(uint64)n;
    uint64 va = PGROUNDUP(old);
    for (; va < PGROUNDUP(next); va += PGSIZE)
      if (add_page(p->pagetable, va, PTE_R|PTE_W) < 0) {
        uvmunmap(p->pagetable, PGROUNDUP(old), (va-PGROUNDUP(old))/PGSIZE, 1);
        return (uint64)-1;
      }
  } else {
    uint64 shrink = -(long)n;
    if (shrink > old-p->heap_base) return (uint64)-1;
    next = old-shrink;
    uvmunmap(p->pagetable, PGROUNDUP(next), (PGROUNDUP(old)-PGROUNDUP(next))/PGSIZE, 1);
  }
  p->sz = next;
  sfence_vma();
  return old;
}

static void __attribute__((noreturn)) run_process(struct proc *p)
{
  intr_off();
  current = p;
  p->state = PROC_RUNNING;
  boot_trapframe_select((uint64)p->frame);
  usertrapret(MAKE_SATP(p->pagetable));
}

// All continuations are saved user frames; switch only at user trap boundaries
// or before read has consumed anything, where the ecall can safely be restarted.
void proc_yield(int restart_read)
{
  if (!managed) return;
  struct proc *p = myproc();
  int first = (int)(p-processes);
  for (int n=1; n<PROCESS_SLOTS; n++) {
    struct proc *next = &processes[(first+n)%PROCESS_SLOTS];
    if (next->state != PROC_RUNNABLE) continue;
    if (restart_read) p->frame->epc -= 4;
    p->state = PROC_RUNNABLE;
    run_process(next);
  }
}

void proc_boot_init(void)
{
  clear(&boot_process, sizeof(boot_process));
  boot_process.pid = 1;
  boot_process.state = PROC_RUNNING;
  current = &boot_process;
  managed = 0;
}

struct proc *myproc(void)
{
  return current ? current : &boot_process;
}

void proc_shell_launch(void)
{
  intr_off();
  managed = 1;
  next_pid = 1;
  struct proc *p = allocate_process();
  if (!p || load_image(p, "sh") < 0) {
    printf("cannot load embedded sh\n"); proc_exit_idle();
  }
  dump_pagetable(p->pagetable);
  run_process(p);
}

int proc_fork(void)
{
  if (!managed) return -1;
  struct proc *parent = myproc();
  struct proc *child = allocate_process();
  if (!child) return -1;
  child->parent_pid = parent->pid;
  child->image_size = parent->image_size;
  child->sz = parent->sz;
  child->heap_base = parent->heap_base;
  child->guard = parent->guard;
  for (uint64 va = 0; va < parent->sz; va += PGSIZE) {
    pte_t *pte = walk(parent->pagetable, va, 0);
    if (!pte || !(*pte & PTE_V)) continue;
    if (add_page(child->pagetable, va, PTE_FLAGS(*pte)) < 0) {
      release_process(child); return -1;
    }
    copy((void *)PTE2PA(*walk(child->pagetable, va, 0)),
         (void *)PTE2PA(*pte), PGSIZE);
  }
  copy(child->frame, parent->frame, sizeof(*child->frame));
  child->frame->a0 = 0;
  return (int)child->pid;
}

int proc_exec(uint64 name_address)
{
  if (!managed) return -1;
  char name[32];
  uint64 i;
  for (i = 0; i < sizeof(name); i++) {
    if (name_address >= MAXVA || i >= MAXVA - name_address ||
        user_copyin(myproc()->pagetable, &name[i], name_address + i, 1) < 0) return -1;
    if (!name[i]) break;
  }
  if (i == sizeof(name)) return -1;
  // Gift gets keeps the line terminator.
  while (i && (name[i - 1] == '\n' || name[i - 1] == '\r' || name[i - 1] == ' '))
    name[--i] = 0;
  if (!i) return -1;
  return load_image(myproc(), name);
}

int proc_wait(uint64 status_address)
{
  if (!managed) return -1;
  struct proc *parent = myproc();
  if (status_address && !user_writable(parent->pagetable, status_address, sizeof(int))) return -1;
  struct proc *ready = 0;
  for (int i = 0; i < PROCESS_SLOTS; i++) {
    struct proc *p = &processes[i];
    if (p->state == PROC_UNUSED || p->parent_pid != parent->pid) continue;
    if (p->state == PROC_EXITED) {
      int status = (int)p->exit_status;
      if (status_address && user_copyout(parent->pagetable, status_address, &status, sizeof(status)) < 0) return -1;
      int pid = (int)p->pid;
      release_process(p);
      return pid;
    }
    if (!ready && p->state == PROC_RUNNABLE) ready = p;
  }
  if (!ready) return -1;
  parent->wait_address = status_address;
  parent->state = PROC_WAITING;
  // User continuation is in its frame; discard the temporary C call chain.
  run_process(ready);
}

void proc_exit(int status)
{
  intr_off();
  struct proc *p = myproc();
  p->exit_status = (uint64)(long)status;
  p->state = PROC_EXITED;
  if (!managed) proc_exit_idle();
  for (int i = 0; i < PROCESS_SLOTS; i++) {
    struct proc *parent = &processes[i];
    if (parent->pid != p->parent_pid || parent->state != PROC_WAITING) continue;
    int result = (int)p->pid;
    if (parent->wait_address && user_copyout(parent->pagetable, parent->wait_address, &status, sizeof(status)) < 0) result = -1;
    parent->frame->a0 = (uint64)(long)result;
    deferred = p;
    run_process(parent);
  }
  for (int i = 0; i < PROCESS_SLOTS; i++) {
    if (processes[i].parent_pid == p->pid) processes[i].parent_pid = 0;
  }
  for (int i = 0; i < PROCESS_SLOTS; i++)
    if (processes[i].state == PROC_RUNNABLE) run_process(&processes[i]);
  proc_exit_idle();
}
