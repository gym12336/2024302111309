# lab1 骨架 Makefile(课程提供;新增源文件时把它加进 OBJS)
CC   = riscv64-unknown-elf-gcc
LD   = riscv64-unknown-elf-ld
CFLAGS = -Wall -Werror -O -std=gnu99 -mcmodel=medany -ffreestanding \
         -nostdlib -fno-common -ggdb -march=rv64gc -fno-stack-protector -fno-pie
QEMU = qemu-system-riscv64

OBJS = kernel/entry.o kernel/start.o kernel/console.o kernel/printf.o kernel/main.o \
       kernel/userimg.o kernel/trampoline_link.o kernel/boot_vm.o kernel/trap.o \
       kernel/kernel_trap_entry.o kernel/user_boot.o kernel/user_probe.o \
       kernel/proc.o kernel/syscall.o kernel/user_mem.o kernel/plic.o

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
