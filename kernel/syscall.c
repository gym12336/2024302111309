#include "syscall_dispatch.h"
#include "syscall.h"
#include "proc.h"
#include "user_mem.h"
#include "console.h"
#include "vm_ops.h"
#include "vm_debug.h"

extern void uartputc_sync(int c);

static uint64
argraw(struct trapframe *tf, int index)
{
  switch (index) {
  case 0: return tf->a0;
  case 1: return tf->a1;
  case 2: return tf->a2;
  default: return 0;
  }
}

static uint64
sys_write(struct trapframe *tf)
{
  uint64 fd = argraw(tf, 0);
  uint64 address = argraw(tf, 1);
  uint64 length = argraw(tf, 2);
  // Only console stdout/stderr exist now. Count must be a nonnegative int.
  if ((fd != 1 && fd != 2) || length > 0x7fffffffUL)
    return (uint64)-1;
  if (!user_readable(myproc()->pagetable, address, length))
    return (uint64)-1;
  uint8 buffer[64];
  for (uint64 done = 0; done < length;) {
    uint64 chunk = length - done;
    if (chunk > sizeof(buffer))
      chunk = sizeof(buffer);
    if (user_copyin(myproc()->pagetable, buffer, address + done, chunk) < 0)
      return (uint64)-1;
    for (uint64 i = 0; i < chunk; i++)
      uartputc_sync(buffer[i]); // Raw user bytes; Lab1's banner uses putchar().
    done += chunk;
  }
  return length;
}

static uint64
sys_read(struct trapframe *tf)
{
  uint64 fd = argraw(tf, 0);
  uint64 address = argraw(tf, 1);
  uint64 length = argraw(tf, 2);
  if (fd != 0 || length > 0x7fffffffUL)
    return (uint64)-1;
  return (uint64)(long)console_read(myproc()->pagetable, address, length);
}

static uint64
sys_getpid(void)
{
  return myproc()->pid;
}

uint64
syscall_dispatch(struct trapframe *tf)
{
  // Compare the full 64-bit register, so large invalid numbers cannot alias 11.
  switch (tf->a7) {
  case SYS_dump_pagetable:
    dump_pagetable(myproc()->pagetable);
    return 0;
  case SYS_sbrk:
    return proc_sbrk((int)(uint32)argraw(tf, 0));
  case SYS_getpid:
    return sys_getpid();
  case SYS_write:
    return sys_write(tf);
  case SYS_read:
    return sys_read(tf);
  case SYS_fork:
    return (uint64)(long)proc_fork();
  case SYS_exec:
    // Course sh uses exec(name, argv); argv is intentionally unused in lab2.
    return (uint64)(long)proc_exec(argraw(tf, 0));
  case SYS_wait:
    return (uint64)(long)proc_wait(argraw(tf, 0));
  case SYS_exit:
    // The user contract takes int: interpret the low 32 bits as signed status.
    proc_exit((int)(uint32)argraw(tf, 0));
  default:
    return (uint64)-1;
  }
}
