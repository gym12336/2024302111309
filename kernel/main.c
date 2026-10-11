#include "course_sid.h"
#include "trap.h"

extern void printf(const char *format, ...);
extern void boot_vm_init(void);
extern void user_probe_launch(void) __attribute__((noreturn));

void
main(void)
{
  boot_vm_init();
  trap_init();

  printf("OSLAB1 sid=%lu mod97=0x%lx\n",
         (unsigned long)COURSE_SID,
         (unsigned long)(COURSE_SID % 97UL));

  printf("SELFTEST zero=%d neg=%d max=%d empty=[%s]\n",
         0, -123, 2147483647, "");

  printf("SELFTEST long=%s\n",
         "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
         "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789");

  user_probe_launch();
}
