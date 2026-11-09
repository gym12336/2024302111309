#include "proc.h"
#include "riscv.h"
#include "memlayout.h"
#include "trapframe.h"
#include "trap.h"
#include "user_mem.h"
#include "vm_ops.h"
#include "kalloc.h"
#include "course_sid.h"
#include "param.h"
#include "smp_stats.h"

extern char kernel_end[], trampoline[], _uprog_table[];
extern void proc_exit_idle(void) __attribute__((noreturn));
extern void printf(const char *, ...);

struct image_meta { const char *name; uint64 entry; uint64 memory; uint64 data; };
#include "user_meta.h"

static struct proc boot_process;
static struct proc processes[NPROC];
static struct cpu cpus[NCPU];
static struct proc *initproc;
static struct spinlock pid_lock, wait_lock, tickslock, scheduler_lock;
static uint64 ticks;
static uint64 online_mask;
static int initialized;
static int rr_idx = -1;
extern void swtch(struct context *, struct context *);
static void forkret(void) __attribute__((noreturn));

static uint64 next_pid;
static int managed;
static void release_process(struct proc *p);

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
  // The lock must survive slot reuse, including its current ownership.
  clear((uint8 *)p + sizeof(p->lock), sizeof(*p) - sizeof(p->lock));
}

static struct proc *allocate_process(void)
{
  for (int i = 0; i < NPROC; i++) {
    struct proc *p = &processes[i];
    acquire(&p->lock);
    if (p->state != PROC_UNUSED) { release(&p->lock); continue; }
    p->state = PROC_USED;
    p->frame = kalloc();
    void *stack = kalloc();
    p->kernel_stack = stack ? (uint64)stack+PGSIZE : 0;
    if (!p->frame || !stack || !(p->pagetable = new_table(p))) {
      release_process(p); release(&p->lock); return 0;
    }
    acquire(&pid_lock);
    p->pid = next_pid++;
    release(&pid_lock);
    p->context.ra = (uint64)forkret;
    p->context.sp = p->kernel_stack;
    p->tickets = 7 + COURSE_SID % 13;
    p->base_priority = p->priority = 1;
    // Return USED with p->lock held; publish only after loading/copying.
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

// A runnable process has not consumed any of its next waiting interval.
static void ready(struct proc *p)
{
  p->state = PROC_RUNNABLE;
  p->ready_ticks = 0;
  p->priority = p->base_priority;
}

struct cpu *mycpu(void)
{
  return &cpus[r_tp()]; // Call with interrupts disabled; uservec restores hart tp.
}

struct proc *myproc(void)
{
  push_off();
  struct proc *p = mycpu()->proc;
  pop_off();
  return p ? p : &boot_process; // Retain the isolated LAB2_BOOT_PROBE path.
}

void proc_boot_init(void)
{
  if (initialized) return;
  initialized = 1;
  initlock(&pid_lock, "pid");
  initlock(&wait_lock, "wait");
  initlock(&tickslock, "ticks");
  initlock(&scheduler_lock, "scheduler");
  for (int i = 0; i < NPROC; i++) initlock(&processes[i].lock, "proc");
  initlock(&boot_process.lock, "boot");
  boot_process.pid = 1;
  boot_process.state = PROC_RUNNING;
  boot_process.frame = (struct trapframe *)TRAPFRAME;
  next_pid = 1;
}

void sched(void)
{
  struct proc *p = myproc();
  struct cpu *c = mycpu();
  if (!holding(&p->lock)) panic("sched p->lock");
  if (c->noff != 1) panic("sched locks");
  if (p->state == PROC_RUNNING) panic("sched running");
  if (intr_get()) panic("sched interruptible");
  int intena = c->intena;
  swtch(&p->context, &c->context);
  mycpu()->intena = intena;
}

void yield(void)
{
  if (!managed) return;
  struct proc *p = myproc();
  acquire(&p->lock);
  ready(p);
  sched();
  release(&p->lock);
}

void sleep(void *chan, struct spinlock *lk)
{
  struct proc *p = myproc();
  if (lk == &p->lock) panic("sleep condition lock");
  // Acquire the process lock before giving up the condition lock: wakeup
  // cannot pass the sleeper between its last condition check and SLEEPING.
  acquire(&p->lock);
  release(lk);
  p->chan = chan;
  p->state = PROC_SLEEPING;
  sched();
  p->chan = 0;
  release(&p->lock);
  acquire(lk);
}

void wakeup(void *chan)
{
  struct proc *self = myproc();
  for (int i = 0; i < NPROC; i++) {
    struct proc *p = &processes[i];
    if (p == self) continue;
    acquire(&p->lock);
    if (p->state == PROC_SLEEPING && p->chan == chan) ready(p);
    release(&p->lock);
  }
}

void scheduler(void)
{
  struct cpu *c = mycpu();
  c->proc = 0;
  __atomic_fetch_or(&online_mask, 1UL << r_tp(), __ATOMIC_RELEASE);
  for (;;) {
    // Interrupts deliver wakeups on this hart; the selection lock serializes
    // the shared cursor and reservation against the other scheduler.
    intr_on();
    intr_off();
    acquire(&scheduler_lock);
    struct proc *best = 0;
    int chosen = -1, best_priority = -1;
    for (int n = 1; n <= NPROC; n++) {
      int i = (rr_idx + n) % NPROC;
      struct proc *p = &processes[i];
      acquire(&p->lock);
      if (p->state == PROC_RUNNABLE &&
          (!best || p->priority > best_priority)) {
        best = p;
        chosen = i;
        best_priority = p->priority;
      }
      release(&p->lock);
    }
    if (!best) {
      release(&scheduler_lock);
      asm volatile("wfi");
      continue;
    }
    acquire(&best->lock);
    if (best->state != PROC_RUNNABLE) panic("scheduler reservation");
    rr_idx = chosen;
    best->state = PROC_RUNNING;
    best->ready_ticks = 0;
    best->priority = best->base_priority; // An aging boost buys one dispatch.
    best->last_slice_ticks = 0;
    c->proc = best;
    __atomic_fetch_add(&c->dispatches, 1, __ATOMIC_RELAXED);
    release(&scheduler_lock); // sched() must see only p->lock, even on SMP.
    swtch(&c->context, &best->context);
    c->proc = 0;
    release(&best->lock);
  }
}

static void forkret(void)
{
  struct proc *p = myproc();
  release(&p->lock); // First dispatch does not return through sched().
  usertrapret(MAKE_SATP(p->pagetable));
}

void proc_shell_init(void)
{
  managed = 1;
  struct proc *p = allocate_process();
  if (!p || load_image(p, "sh") < 0) panic("load sh");
  initproc = p;
  dump_pagetable(p->pagetable);
  ready(p);
  release(&p->lock);
}

void proc_shell_launch(void)
{
  proc_shell_init();
  scheduler();
}

int proc_fork(void)
{
  if (!managed) return -1;
  struct proc *parent = myproc();
  struct proc *child = allocate_process();
  if (!child) return -1;
  child->image_size = parent->image_size;
  child->sz = parent->sz;
  child->heap_base = parent->heap_base;
  child->guard = parent->guard;
  child->base_priority = child->priority = parent->base_priority;
  child->tickets = parent->tickets;
  for (uint64 va = 0; va < parent->sz; va += PGSIZE) {
    pte_t *pte = walk(parent->pagetable, va, 0);
    if (!pte || !(*pte & PTE_V)) continue;
    if (add_page(child->pagetable, va, PTE_FLAGS(*pte)) < 0) {
      release_process(child);
      release(&child->lock);
      return -1;
    }
    copy((void *)PTE2PA(*walk(child->pagetable, va, 0)),
         (void *)PTE2PA(*pte), PGSIZE);
  }
  copy(child->frame, parent->frame, sizeof(*child->frame));
  child->frame->a0 = 0;
  int pid = (int)child->pid;
  release(&child->lock);
  acquire(&wait_lock);
  child->parent = parent;
  release(&wait_lock);
  acquire(&child->lock);
  ready(child);
  release(&child->lock);
  return pid;
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
  while (i && (name[i-1] == '\n' || name[i-1] == '\r' || name[i-1] == ' ')) name[--i] = 0;
  return i ? load_image(myproc(), name) : -1;
}

int proc_wait(uint64 status_address)
{
  if (!managed) return -1;
  struct proc *parent = myproc();
  if (status_address && !user_writable(parent->pagetable, status_address, sizeof(int))) return -1;
  acquire(&wait_lock);
  for (;;) {
    int children = 0;
    for (int i = 0; i < NPROC; i++) {
      struct proc *p = &processes[i];
      if (p->parent != parent) continue;
      acquire(&p->lock);
      children = 1;
      if (p->state == PROC_ZOMBIE) {
        int pid = (int)p->pid, status = p->exit_status;
        if (status_address && user_copyout(parent->pagetable, status_address, &status, sizeof(status)) < 0) {
          release(&p->lock); release(&wait_lock); return -1;
        }
        release_process(p);
        release(&p->lock);
        release(&wait_lock);
        return pid;
      }
      release(&p->lock);
    }
    if (!children || proc_killed()) { release(&wait_lock); return -1; }
    sleep(parent, &wait_lock);
  }
}

void proc_exit(int status)
{
  if (!managed) {
    intr_off(); // The isolated boot probe terminates in a frozen idle loop.
    myproc()->exit_status = status;
    myproc()->state = PROC_ZOMBIE;
    proc_exit_idle();
  }
  struct proc *p = myproc();
  if (p == initproc) panic("shell exited");
  acquire(&wait_lock);
  for (int i = 0; i < NPROC; i++) {
    if (processes[i].parent == p) {
      processes[i].parent = initproc;
      wakeup(initproc);
    }
  }
  wakeup(p->parent);
  acquire(&p->lock);
  p->exit_status = status;
  p->state = PROC_ZOMBIE;
  release(&wait_lock);
  sched();
  panic("zombie returned");
}

void proc_clock(void)
{
  if (r_tp() != 0) return; // Global time/aging advance once, not once per hart.
  acquire(&tickslock);
  ticks++;
  wakeup(&ticks);
  release(&tickslock);
  // Only RUNNABLE time counts toward aging; blocked processes wait on events.
  for (int i = 0; i < NPROC; i++) {
    struct proc *p = &processes[i];
    acquire(&p->lock);
    if (p->state == PROC_RUNNABLE && p->priority == 0 && ++p->ready_ticks >= 8) {
      p->priority = 1;
      p->ready_ticks = 0;
    }
    release(&p->lock);
  }
}

void proc_user_tick(void)
{
  if (!managed) return;
  struct proc *p = myproc();
  acquire(&p->lock);
  p->cpu_ticks++;
  p->last_slice_ticks++;
  __atomic_fetch_add(&mycpu()->user_ticks, 1, __ATOMIC_RELAXED);
  int expired = p->last_slice_ticks >= LAB2_TICK;
  release(&p->lock);
  if (expired) yield();
}

uint64 proc_uptime(void)
{
  acquire(&tickslock);
  uint64 value = ticks;
  release(&tickslock);
  return value;
}

int proc_pause(int n)
{
  if (n < 0) return -1;
  acquire(&tickslock);
  uint64 start = ticks;
  while (ticks - start < (uint64)n) {
    if (proc_killed()) { release(&tickslock); return -1; }
    sleep(&ticks, &tickslock);
  }
  release(&tickslock);
  return 0;
}

int proc_killed(void)
{
  struct proc *p = myproc();
  acquire(&p->lock);
  int killed = p->killed;
  release(&p->lock);
  return killed;
}

int proc_kill(int pid)
{
  for (int i = 0; i < NPROC; i++) {
    struct proc *p = &processes[i];
    acquire(&p->lock);
    if (p->pid == (uint64)pid && p->state != PROC_UNUSED && p->state != PROC_ZOMBIE) {
      p->killed = 1;
      if (p->state == PROC_SLEEPING) ready(p);
      release(&p->lock);
      return 0;
    }
    release(&p->lock);
  }
  return -1;
}

int proc_schedstat(int pid, uint64 cpu_address, uint64 slice_address)
{
  struct proc *caller = myproc();
  if (!user_writable(caller->pagetable, cpu_address, sizeof(int)) ||
      !user_writable(caller->pagetable, slice_address, sizeof(int))) return -1;
  uint64 target = pid == -1 ? caller->pid : (uint64)pid;
  int cpu = 0, slice = 0, found = 0;
  for (int i = 0; i < NPROC; i++) {
    struct proc *p = &processes[i];
    acquire(&p->lock);
    if (p->pid == target && p->state != PROC_UNUSED && p->state != PROC_USED && p->state != PROC_ZOMBIE) {
      cpu = p->cpu_ticks;
      slice = p->last_slice_ticks;
      found = 1;
    }
    release(&p->lock);
    if (found) break;
  }
  if (!found) return -1;
  // Snapshot under the target lock; access user pages only after releasing it.
  if (user_copyout(caller->pagetable, cpu_address, &cpu, sizeof(cpu)) < 0 ||
      user_copyout(caller->pagetable, slice_address, &slice, sizeof(slice)) < 0) return -1;
  return 0;
}

int proc_setickets(int tickets)
{
  if (tickets < 1) return -1;
  struct proc *p = myproc();
  acquire(&p->lock);
  p->tickets = tickets;
  release(&p->lock);
  return 0;
}

int proc_setpriority(int priority)
{
  if (priority < 0 || priority > 1) return -1;
  struct proc *p = myproc();
  acquire(&p->lock);
  int old = p->base_priority;
  p->base_priority = p->priority = priority;
  p->ready_ticks = 0;
  release(&p->lock);
  return old;
}

int proc_smpstat(uint64 address)
{
  struct proc *caller = myproc();
  if (!user_writable(caller->pagetable, address, sizeof(struct smp_stats))) return -1;
  struct smp_stats stats;
  clear(&stats, sizeof(stats));
  stats.online_mask = __atomic_load_n(&online_mask, __ATOMIC_ACQUIRE);
  for (int i = 0; i < NCPU; i++) {
    stats.dispatches[i] = __atomic_load_n(&cpus[i].dispatches, __ATOMIC_RELAXED);
    stats.user_ticks[i] = __atomic_load_n(&cpus[i].user_ticks, __ATOMIC_RELAXED);
  }
  struct kalloc_stats memory;
  if (kalloc_get_stats(&memory) < 0) return -1;
  stats.free_pages = memory.free_pages;
  return user_copyout(caller->pagetable, address, &stats, sizeof(stats));
}
