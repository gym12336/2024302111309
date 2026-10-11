#!/usr/bin/env python3
"""Exercise actual console ring code in isolated RISC-V kernels, in both modes."""
import pathlib
import re
import socket
import subprocess
import tempfile
import time


def run_case(folder, mode):
    source = folder / "ring.c"
    source.write_text(r'''
#include "course_sid.h"
#undef LAB2_BUF_SEMANTICS
#define LAB2_BUF_SEMANTICS TEST_SEMANTICS
// Include the production implementation so the probe can seed wrap counters.
#include "console.c"
#include "trap.h"
extern void boot_vm_init(void);
volatile uint64 ring_result;
static void check(int ok, uint64 code)
{
  if (!ok) {
    intr_off();
    ring_result = code;
    for (;;) asm volatile("wfi");
  }
}
void main(void)
{
  boot_vm_init();
  trap_init();
  uart_init();
  intr_off();
  check(console_getc() == -1 && !intr_get(), 1);
  intr_on();
  check(console_getc() == -1 && intr_get(), 2);
  console_input(0);
  console_input('A');
  check(intr_get(), 3);
#if TEST_SEMANTICS == 0
  check(console_getc() == -1 && input.w == 0 && input.e == 2, 4);
  console_input('\n');
#endif
  check(console_getc() == 0 && console_getc() == 'A', 5);
#if TEST_SEMANTICS == 0
  check(console_getc() == '\n', 6);
#endif
  check(console_getc() == -1, 7);
  uint64 start = input.r;
  for (uint64 i = 0; i < LAB2_BUF_SIZE; i++)
    console_input(0x20 + i);
  check(input.e - input.r == LAB2_BUF_SIZE && input.w == input.e, 8);
  console_input('X');
  console_input('Y');
  check(input.dropped == 2 && input.e == start + LAB2_BUF_SIZE, 9);
  for (uint64 i = 0; i < 10; i++)
    check(console_getc() == 0x20 + i, 10);
  for (uint64 i = 0; i < 10; i++)
    console_input('a' + i);
  check(input.e - input.r == LAB2_BUF_SIZE && input.w == input.e, 11);
  for (uint64 i = 10; i < LAB2_BUF_SIZE; i++)
    check(console_getc() == 0x20 + i, 12);
  for (uint64 i = 0; i < 10; i++)
    check(console_getc() == 'a' + i, 13);
  check(console_getc() == -1 && input.r == input.w && input.w == input.e, 14);
  // Force the real unsigned counters across 2^64, without a long runtime.
  input.r = input.w = input.e = ~(uint64)0 - 2;
  char wrap[] = {'w', 'r', 'a', 'p', '\n'};
  for (uint64 i = 0; i < 5; i++) console_input(wrap[i]);
  check(input.e == 2 && input.e - input.r == 5, 15);
  for (uint64 i = 0; i < 5; i++) check(console_getc() == wrap[i], 16);
  check(input.r == 2 && input.w == 2 && console_getc() == -1, 17);
  input.r = input.w = input.e = 0;
  char lines[] = {'x', 'y', '\n', 'z'};
  for (uint64 i = 0; i < 4; i++) console_input(lines[i]);
  check(console_getc() == 'x' && console_getc() == 'y' && console_getc() == '\n', 18);
#if TEST_SEMANTICS == 0
  check(input.w == 3 && input.e == 4 && console_getc() == -1, 19);
  console_input('\n');
  check(console_getc() == 'z' && console_getc() == '\n', 20);
#else
  check(console_getc() == 'z', 21);
#endif
  check(console_getc() == -1, 22);
  intr_off();
  console_input('\n');
  check(console_getc() == '\n' && !intr_get(), 23);
  ring_result = 0x50415353;
  for (;;) asm volatile("wfi");
}
''')
    obj, kernel = folder / "ring.o", folder / "kernel.elf"
    flags = ["-Wall", "-Werror", "-O", "-std=gnu99", "-mcmodel=medany", "-ffreestanding",
             "-nostdlib", "-fno-common", "-march=rv64gc", "-fno-stack-protector", "-fno-pie", "-Ikernel"]
    subprocess.run(["riscv64-unknown-elf-gcc"] + flags + [f"-DTEST_SEMANTICS={mode}", "-c", str(source), "-o", str(obj)], check=True)
    objects = "entry start printf userimg trampoline_link boot_vm trap kernel_trap_entry proc syscall user_mem plic".split()
    subprocess.run(["riscv64-unknown-elf-ld", "-T", "kernel/kernel.ld", "-o", str(kernel)] +
                   [f"kernel/{name}.o" for name in objects] + [str(obj)], check=True)
    symbols = {}
    for line in subprocess.check_output(["riscv64-unknown-elf-nm", str(kernel)], text=True).splitlines():
        parts = line.split()
        if len(parts) == 3:
            symbols[parts[2]] = int(parts[0], 16)
    serial, monitor, traps = [folder / name for name in ("serial", "monitor.sock", "traps")]
    process = subprocess.Popen([
        "qemu-system-riscv64", "-machine", "virt", "-bios", "none", "-kernel", str(kernel),
        "-display", "none", "-serial", "file:" + str(serial), "-monitor", f"unix:{monitor},server,nowait",
        "-d", "int", "-D", str(traps),
    ], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        deadline = time.monotonic() + 10
        while not monitor.exists():
            if process.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError("QEMU did not start")
            time.sleep(0.02)
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as control:
            control.settimeout(3)
            control.connect(str(monitor))

            def receive():
                data = b""
                while b"(qemu) " not in data:
                    chunk = control.recv(65536)
                    if not chunk:
                        raise RuntimeError("monitor closed")
                    data += chunk
                return data.decode(errors="replace")

            receive()

            def command(value):
                control.sendall(value.encode() + b"\n")
                return receive()

            while True:
                command("stop")
                output = command(f"xp /1gx 0x{symbols['ring_result']:x}")
                # A single word following the address is the observable result.
                match = re.search(r"^[0-9a-fA-F]+:\s+0x([0-9a-fA-F]+)", output, re.M)
                result = int(match[1], 16) if match else 0
                if result:
                    break
                if time.monotonic() > deadline:
                    raise RuntimeError("ring probe timed out: " + traps.read_text()[:1500])
                command("cont")
                time.sleep(0.02)
            if result != 0x50415353:
                raise RuntimeError(f"mode {mode}: ring assertion {result} failed")
        expected = b"\x00A" + (b"\n" if mode == 0 else b"")
        expected += bytes(range(0x20, 0x20 + 64)) + b"abcdefghijwrap\nxy\nz"
        expected += (b"\n" if mode == 0 else b"") + b"\n"
        if serial.read_bytes() != expected or traps.read_bytes():
            raise RuntimeError("accepted-byte echo mismatch or unexpected hardware trap")
        name = "line" if mode == 0 else "stream"
        print(f"PASS: {name} ring: empty/NUL, all 64 slots, drop 2 new bytes, FIFO and slot reuse")
        print(f"PASS: {name} ring: uint64 counter wrap; interrupt state preserved; exact accepted-byte echo")
        if mode == 0:
            print("PASS: line ring hides partial lines; newline and full capacity commit readable data")
        else:
            print("PASS: stream ring makes each byte readable immediately without newline")
    finally:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        process.stderr.close()


if __name__ == "__main__":
    for mode in (1, 0):
        with tempfile.TemporaryDirectory(prefix="lab2-ring-") as folder:
            run_case(pathlib.Path(folder), mode)
