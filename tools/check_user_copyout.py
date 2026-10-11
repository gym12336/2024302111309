#!/usr/bin/env python3
"""Check actual user copyout against isolated 4 KiB user mappings in QEMU."""
import pathlib
import subprocess
import tempfile
import time


def main():
    with tempfile.TemporaryDirectory(prefix="lab2-copyout-") as folder:
        folder = pathlib.Path(folder)
        source = folder / "probe.c"
        source.write_text(r'''
#include "types.h"
#include "riscv.h"
#include "memlayout.h"
#include "user_mem.h"
#include "uart.h"
#include "trap.h"
extern void boot_vm_init(void);
extern void printf(const char *, ...);
static uint64 table[512] __attribute__((aligned(PGSIZE)));
static uint64 l1[512] __attribute__((aligned(PGSIZE)));
static uint64 l0[512] __attribute__((aligned(PGSIZE)));
static uint8 data[3][PGSIZE] __attribute__((aligned(PGSIZE)));
static void check(int ok, int code)
{
  if (!ok) {
    printf("copyout check failed: %d\n", code);
    for (;;) asm volatile("wfi");
  }
}
void main(void)
{
  boot_vm_init();
  trap_init();
  table[0] = PA2PTE(l1) | PTE_V;
  l1[0] = PA2PTE(l0) | PTE_V;
  l0[4] = PA2PTE(data[0]) | PTE_V | PTE_R | PTE_W | PTE_U;
  l0[5] = PA2PTE(data[2]) | PTE_V | PTE_R | PTE_W | PTE_U;
  l0[6] = PA2PTE(data[1]) | PTE_V | PTE_R | PTE_X | PTE_U;
  l0[7] = PA2PTE(data[1]) | PTE_V | PTE_R | PTE_W;
  l0[9] = PA2PTE(data[1]) | PTE_V | PTE_W | PTE_U;
  for (uint64 page = 0; page < 3; page++)
    for (uint64 i = 0; i < PGSIZE; i++) data[page][i] = 0xa5;
  uint8 bytes[] = {0, 'A', 255, '\n', 'B', 0};
  uint8 copied[6];
  check(user_writable(table, 0x4ffe, 6), 1);
  check(user_copyout(table, 0x4ffe, bytes, 6) == 0, 2);
  for (uint64 page = 0; page < 3; page++) {
    for (uint64 i = 0; i < PGSIZE; i++) {
      uint8 expected = 0xa5;
      if (page == 0 && i >= PGSIZE - 2) expected = bytes[i - (PGSIZE - 2)];
      if (page == 2 && i < 4) expected = bytes[i + 2];
      check(data[page][i] == expected, 3);
    }
  }
  check(user_copyin(table, copied, 0x4ffe, 6) == 0, 4);
  for (uint64 i = 0; i < 6; i++) check(copied[i] == bytes[i], 5);
  check(user_readable(table, 0x6000, 1) && !user_writable(table, 0x6000, 1), 6);
  check(user_copyin(table, copied, 0x6000, 1) == 0 && copied[0] == 0xa5, 21);
  check(user_copyout(table, 0x6000, bytes, 1) == -1, 7);
  check(user_copyout(table, 0x7000, bytes, 1) == -1, 8);
  check(user_copyout(table, 0x8000, bytes, 1) == -1, 9);
  check(user_copyout(table, 0x9000, bytes, 1) == -1, 10);
  check(user_copyout(table, 0x5fff, bytes, 2) == -1 && data[2][4095] == 0xa5, 11);
  check(user_copyout(table, 0x4ffe, bytes, 0xffffffffffffffffUL) == -1, 12);
  check(user_copyout(table, MAXVA - 1, bytes, 2) == -1, 13);
  check(user_copyout(table, MAXVA, bytes, 1) == -1, 14);
  check(user_copyout(0, 0x4000, bytes, 1) == -1, 15);
  check(user_copyout(0, ~(uint64)0, 0, 0) == 0, 16);
  uint64 saved = l0[4];
  l0[4] = PA2PTE(UART0) | PTE_V | PTE_R | PTE_W | PTE_U;
  check(user_copyout(table, 0x4000, bytes, 1) == -1, 17);
  l0[4] = saved;
  table[0] = PA2PTE(data[0]) | PTE_V | PTE_R | PTE_W | PTE_U;
  check(user_copyout(table, 0x4000, bytes, 1) == -1, 18);
  table[0] = PA2PTE(l1) | PTE_V;
  for (uint64 i = 0; i < PGSIZE; i++) check(data[1][i] == 0xa5, 19);
  check(data[2][4095] == 0xa5, 20);
  char *message = "COPYOUT PASS\n";
  for (int i = 0; message[i]; i++) uartputc_sync(message[i]);
  for (;;) asm volatile("wfi");
}
''')
        obj, kernel = folder / "probe.o", folder / "kernel.elf"
        flags = ["-Wall", "-Werror", "-O", "-std=gnu99", "-mcmodel=medany", "-ffreestanding",
                 "-nostdlib", "-fno-common", "-march=rv64gc", "-fno-stack-protector", "-fno-pie", "-Ikernel"]
        subprocess.run(["riscv64-unknown-elf-gcc"] + flags + ["-c", str(source), "-o", str(obj)], check=True)
        objects = "entry start console printf userimg trampoline_link boot_vm trap kernel_trap_entry proc syscall user_mem plic".split()
        subprocess.run(["riscv64-unknown-elf-ld", "-T", "kernel/kernel.ld", "-o", str(kernel)] +
                       [f"kernel/{name}.o" for name in objects] + [str(obj)], check=True)
        serial, traps = folder / "serial", folder / "traps"
        process = subprocess.Popen([
            "qemu-system-riscv64", "-machine", "virt", "-bios", "none", "-kernel", str(kernel),
            "-display", "none", "-serial", "file:" + str(serial), "-monitor", "none", "-d", "int", "-D", str(traps),
        ], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 10
            while not serial.exists() or serial.read_bytes() != b"COPYOUT PASS\n":
                output = serial.read_bytes() if serial.exists() else b""
                if output and not b"COPYOUT PASS\n".startswith(output):
                    raise RuntimeError(f"probe failed: {output!r}")
                if process.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError("copyout probe timed out: " + traps.read_text()[:1500])
                time.sleep(0.02)
            if traps.read_bytes():
                raise RuntimeError("unexpected hardware trap: " + traps.read_text())
        finally:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            process.stderr.close()
    print("PASS: copyout crosses two noncontiguous physical pages; binary data and surrounding bytes correct")
    print("PASS: RX/supervisor/unmapped/write-only/device/large-page destinations rejected")
    print("PASS: invalid suffix writes no prefix; range overflow rejected; zero length touches no memory")
    print("PASS: copyin still reads RX pages and returns cross-page data; no unexpected hardware traps")


if __name__ == "__main__":
    main()
