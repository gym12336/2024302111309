#include "proc.h"
#include "riscv.h"
#include "memlayout.h"
#include "trapframe.h"
#include "trap.h"
#include "user_mem.h"

#define PROCESS_SLOTS 4
#define IMAGE_PAGES 16
#define STACK_PAGES 2
#define FRAME_PAGE (IMAGE_PAGES + STACK_PAGES)
#define KSTACK_PAGE (FRAME_PAGE + 1)
#define TABLE_PAGE (KSTACK_PAGE + 2)
#define SLOT_PAGES (TABLE_PAGE + 5)
#define STACK_BOTTOM ((IMAGE_PAGES + 1) * PGSIZE)
#define STACK_TOP (STACK_BOTTOM + STACK_PAGES * PGSIZE)
#define USER_FLAGS (PTE_V | PTE_R | PTE_W | PTE_U | (1UL << 6) | (1UL << 7))

extern char kernel_end[], trampoline[], _uprog_table[];
extern void boot_trapframe_select(uint64);
extern void proc_exit_idle(void) __attribute__((noreturn));
extern void printf(const char *, ...);

struct image_meta { const char *name; uint64 entry; uint64 memory; };
#include "user_meta.h"

static struct proc boot_process;
static struct proc processes[PROCESS_SLOTS];
static struct proc *current;
static uint64 arena_base;
static uint64 next_pid;
static int managed;

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

static void map_user(struct proc *p)
{
  uint64 *root = p->pagetable;
  uint64 *low_l1 = root + 512;
  uint64 *low_l0 = root + 1024;
  uint64 *high_l1 = root + 1536;
  uint64 *high_l0 = root + 2048;
  clear(root, 5 * PGSIZE);
  root[0] = PA2PTE(low_l1) | PTE_V;
  low_l1[0] = PA2PTE(low_l0) | PTE_V;
  for (uint64 va = 0; va < PGROUNDUP(p->image_size); va += PGSIZE)
    low_l0[PX(0, va)] = PA2PTE(p->physical_base + va) | USER_FLAGS | PTE_X;
  for (uint64 i = 0; i < STACK_PAGES; i++)
    low_l0[PX(0, STACK_BOTTOM + i * PGSIZE)] =
      PA2PTE(p->physical_base + (IMAGE_PAGES + i) * PGSIZE) | USER_FLAGS;
  root[PX(2, TRAMPOLINE)] = PA2PTE(high_l1) | PTE_V;
  high_l1[PX(1, TRAMPOLINE)] = PA2PTE(high_l0) | PTE_V;
  high_l0[PX(0, TRAMPOLINE)] = PA2PTE(trampoline) | PTE_V | PTE_R | PTE_X | (1UL << 6);
  high_l0[PX(0, TRAPFRAME)] = PA2PTE(p->frame) | PTE_V | PTE_R | PTE_W | (1UL << 6) | (1UL << 7);
}

static struct proc *allocate_process(void)
{
  for (int i = 0; i < PROCESS_SLOTS; i++) {
    struct proc *p = &processes[i];
    if (p->state != PROC_UNUSED) continue;
    clear(p, sizeof(*p));
    p->physical_base = arena_base + i * SLOT_PAGES * PGSIZE;
    clear((void *)p->physical_base, SLOT_PAGES * PGSIZE);
    p->pagetable = (uint64 *)(p->physical_base + TABLE_PAGE * PGSIZE);
    p->frame = (struct trapframe *)(p->physical_base + FRAME_PAGE * PGSIZE);
    p->kernel_stack = p->physical_base + TABLE_PAGE * PGSIZE;
    p->pid = next_pid++;
    p->state = PROC_RUNNABLE;
    return p;
  }
  return 0;
}

static int load_image(struct proc *p, const char *name)
{
  uint64 start, size;
  const struct image_meta *meta = find_image(name, &start, &size);
  if (!meta || meta->memory == 0 || meta->memory > IMAGE_PAGES * PGSIZE ||
      size > meta->memory || meta->entry >= size) return -1;
  // Reuse the fixed bank without clearing the active kernel stack.
  clear((void *)p->physical_base, (IMAGE_PAGES + STACK_PAGES) * PGSIZE);
  copy((void *)p->physical_base, (void *)start, size);
  p->image_size = meta->memory;
  map_user(p);
  clear(p->frame, sizeof(*p->frame));
  p->frame->epc = meta->entry;
  p->frame->sp = STACK_TOP;
  return 0;
}

static void __attribute__((noreturn)) run_process(struct proc *p)
{
  intr_off();
  current = p;
  p->state = PROC_RUNNING;
  boot_trapframe_select((uint64)p->frame);
  usertrapret(MAKE_SATP(p->pagetable));
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
  arena_base = PGROUNDUP((uint64)kernel_end);
  if (arena_base + PROCESS_SLOTS * SLOT_PAGES * PGSIZE > PHYSTOP) {
    printf("lab2 process banks exceed RAM\n"); proc_exit_idle();
  }
  managed = 1;
  next_pid = 1;
  struct proc *p = allocate_process();
  if (!p || load_image(p, "sh") < 0) {
    printf("cannot load embedded sh\n"); proc_exit_idle();
  }
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
  copy((void *)child->physical_base, (void *)parent->physical_base,
       (IMAGE_PAGES + STACK_PAGES) * PGSIZE);
  map_user(child);
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
      p->state = PROC_UNUSED;
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
    p->state = PROC_UNUSED;
    run_process(parent);
  }
  for (int i = 0; i < PROCESS_SLOTS; i++) {
    if (processes[i].parent_pid == p->pid) processes[i].parent_pid = 0;
  }
  for (int i = 0; i < PROCESS_SLOTS; i++)
    if (processes[i].state == PROC_RUNNABLE) run_process(&processes[i]);
  proc_exit_idle();
}
