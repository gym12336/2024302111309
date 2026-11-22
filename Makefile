# lab1 骨架 Makefile(课程提供;新增源文件时把它加进 OBJS)
CC   = riscv64-unknown-elf-gcc
LD   = riscv64-unknown-elf-ld
CFLAGS = -Wall -Werror -O -std=gnu99 -mcmodel=medany -ffreestanding \
         -nostdlib -fno-common -ggdb -march=rv64gc -fno-stack-protector -fno-pie
QEMU = qemu-system-riscv64
CPUS ?= 1
QEMU += -smp $(CPUS)

OBJS = kernel/entry.o kernel/start.o kernel/console.o kernel/printf.o kernel/main.o \
       kernel/userimg.o kernel/trampoline_link.o kernel/boot_vm.o kernel/trap.o \
       kernel/kernel_trap_entry.o kernel/user_boot.o kernel/user_probe.o \
       kernel/kalloc.o kernel/vm_printf.o kernel/vm.o kernel/proc.o kernel/syscall.o kernel/user_mem.o kernel/plic.o
OBJS += kernel/swtch.o kernel/spinlock.o

kernel/kernel: $(OBJS) kernel/kernel.ld
	$(LD) -T kernel/kernel.ld -o $@ $(OBJS)

# Recheck the C/assembly memory contract whenever its header changes.
kernel/trap.o: kernel/trapframe.h kernel/trap.h kernel/types.h kernel/memlayout.h
kernel/main.o: kernel/trap.h kernel/types.h
kernel/user_boot.o: kernel/trapframe.h kernel/trap.h kernel/types.h kernel/memlayout.h
kernel/user_boot.o: kernel/proc.h
kernel/trap.o: kernel/syscall_dispatch.h
kernel/syscall.o: kernel/syscall_dispatch.h kernel/syscall.h kernel/proc.h kernel/trapframe.h kernel/types.h
kernel/proc.o: kernel/proc.h kernel/types.h
kernel/user_probe.o: kernel/syscall.h
kernel/syscall.o: kernel/user_mem.h
kernel/user_mem.o: kernel/user_mem.h kernel/memlayout.h kernel/types.h
kernel/console.o: kernel/uart.h kernel/console.h kernel/memlayout.h
kernel/console.o: kernel/user_mem.h
kernel/syscall.o: kernel/console.h
kernel/plic.o: kernel/plic.h kernel/memlayout.h kernel/types.h
kernel/main.o kernel/trap.o: kernel/uart.h kernel/plic.h
kernel/trampoline_link.o: kernel/trampoline.S kernel/riscv.h kernel/memlayout.h

%.o: %.c kernel/riscv.h kernel/course_sid.h
	$(CC) $(CFLAGS) -Ikernel -c -o $@ $<

%.o: %.S
	$(CC) $(CFLAGS) -Ikernel -c -o $@ $<

# 验收环境固定(排雷环节禁止改动本行以下内容)
qemu: kernel/kernel
	$(QEMU) -machine virt -bios none -kernel kernel/kernel -nographic

clean:
	rm -f kernel/*.o kernel/kernel

# Lab2 赠送规则保持原样，通过 include 并入当前构建。
include Makefile.upgrade

# Lab2 additions around the immutable upgrade rules.
# Gift recipes share ulib.o/printf.o/usys.o; serialize their writes.
.NOTPARALLEL:
UPROGS += badecall bufstorm proctest
UFLAGS += -msmall-data-limit=0 -mno-relax
kernel/userimg.S: $(addprefix user-flat/,$(UPROGS:=.bin))
kernel/main.o kernel/trap.o: kernel/proc.h
$(addprefix user-flat/,$(UPROGS:=.bin)): Makefile
user-flat/badecall.bin: support/tests/badecall.c
user-flat/bufstorm.bin: support/tests/bufstorm.c
kernel/user_meta.h: tools/gen_user_meta.py $(addprefix user-flat/,$(UPROGS:=.bin))
	python3 tools/gen_user_meta.py $(UPROGS) > $@.tmp
	mv $@.tmp $@
kernel/proc.o: kernel/user_meta.h kernel/user_mem.h kernel/trapframe.h kernel/trap.h

# Lab3: derive a page-aligned data boundary without editing the supplied script.
UPROGS += badaccess memcap vmtest vmconcurrent pagedump
user-flat/user-lab3.ld: user/user.ld
	mkdir -p user-flat
	python3 -c 'from pathlib import Path; s=Path("user/user.ld").read_text(); Path("$@").write_text(s.replace("  .data :", "  . = ALIGN(4096); data_start = .;\n  .data :"))'
$(addprefix user-flat/,$(UPROGS:=.bin)): user-flat/user-lab3.ld
# The gifted rule uses LD; this target-local wrapper selects the derived script.
$(addprefix user-flat/,$(UPROGS:=.bin)): LD = python3 tools/link_user.py

kernel/userimg.S kernel/user_meta.h: $(addprefix user-flat/,$(UPROGS:=.bin))

kernel/vm_printf.o: kernel/printf.c

kernel/vm.o kernel/boot_vm.o kernel/proc.o kernel/syscall.o: kernel/vm_ops.h kernel/kalloc.h
kernel/syscall.o: kernel/vm_debug.h
user-flat/pagedump.bin: kernel/vm_debug.h
kernel/console.o: kernel/proc.h

$(addprefix user-flat/,$(UPROGS:=.bin)): Makefile tools/link_user.py

# Lab4 additions; keep the course qemu/clean recipes and supplied rules intact.
UPROGS += bench lottery_test stride_test
UPROGS += alt priority_test schedcheck smptest
UFLAGS += -DSID=2024302111309UL
$(addprefix user-flat/,$(UPROGS:=.bin)): Makefile tools/link_user.py user/common.h user/common.c user-flat/user-lab3.ld
$(addprefix user-flat/,$(UPROGS:=.bin)): LD = python3 tools/link_user.py
kernel/userimg.S kernel/user_meta.h: $(addprefix user-flat/,$(UPROGS:=.bin))
kernel/proc.o kernel/trap.o kernel/console.o kernel/main.o kernel/syscall.o kernel/spinlock.o kernel/user_boot.o: kernel/proc.h kernel/spinlock.h
kernel/kalloc.o kernel/console.o: kernel/spinlock.h
kernel/entry.o: kernel/param.h kernel/course_sid.h
kernel/proc.o: kernel/smp_stats.h kernel/param.h
user-flat/smptest.bin: kernel/smp_stats.h kernel/param.h

# Lab5 course tests.
UPROGS += zerocopy cowpair echo
UPROGS += cowtest
$(addprefix user-flat/,$(UPROGS:=.bin)): Makefile tools/link_user.py user/common.h user/common.c user-flat/user-lab3.ld kernel/syscall.h
$(addprefix user-flat/,$(UPROGS:=.bin)): LD = python3 tools/link_user.py
kernel/userimg.S kernel/user_meta.h: $(addprefix user-flat/,$(UPROGS:=.bin))
# The supplied cowpair source declares an unused variable.
user-flat/cowpair.bin: UFLAGS += -Wno-unused-variable
user-flat/cowtest.bin: kernel/course_sid.h kernel/param.h kernel/smp_stats.h
kernel/main.o kernel/kalloc.o: kernel/kalloc.h
kernel/vm.o: kernel/proc.h
kernel/trap.o kernel/user_mem.o kernel/kalloc.o: kernel/vm_ops.h
