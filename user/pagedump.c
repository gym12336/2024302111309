#include "kernel/types.h"
#include "kernel/vm_debug.h"
#include "user/user.h"
int main(void)
{
  register uint64 number asm("a7") = SYS_dump_pagetable;
  register uint64 result asm("a0");
  asm volatile("ecall" : "=r"(result) : "r"(number) : "memory");
  exit((int)result);
}
