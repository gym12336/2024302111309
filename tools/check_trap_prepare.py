#!/usr/bin/env python3
"""Test trap classification/return preparation in S-mode, without executing sret."""
import pathlib
import re
import socket
import subprocess
import tempfile
import time


def run_case(directory, case):
    source = directory / f"case{case}.c"
    source.write_text('''
#include "trap.c"
extern void boot_vm_init(void);
volatile uint64 observation[6];
void main(void)
{
  boot_vm_init();
  trap_init();
  struct trapframe *tf = (struct trapframe *)TRAPFRAME;
  tf->a0 = 123;
  tf->a1 = 456;
  tf->a7 = 999;
  w_sepc(0x1000);
  asm volatile("csrw stval, %0" : : "r"(0xdeadUL));
  uint64 cause = TEST_CASE == 1 ? 2 :
                 TEST_CASE == 2 ? ((1UL << 63) | 9) : 8;
  asm volatile("csrw scause, %0" : : "r"(cause));
  w_sstatus((r_sstatus() & ~SSTATUS_SPP) |
            (TEST_CASE == 3 ? SSTATUS_SPP : 0));
  handle_user_trap();
  observation[0] = tf->epc;
  observation[1] = tf->a0;
  observation[2] = r_sepc();
  observation[3] = tf->a1;
  observation[4] = tf->a7;
  // Test clearing SPP/SIE, setting SPIE and preserving the unrelated SUM bit.
  w_sstatus((r_sstatus() | SSTATUS_SPP | SSTATUS_SIE | (1UL << 18)) &
            ~SSTATUS_SPIE);
  prepare_return();
  observation[5] = r_satp();
  printf("TRAP-PREPARE READY\\n");
  for (;;) asm volatile("wfi");
}
''', encoding="utf-8")
    obj = directory / f"case{case}.o"
    kernel = directory / f"case{case}.elf"
    subprocess.run([
        "riscv64-unknown-elf-gcc", "-Wall", "-Werror", "-O", "-std=gnu99",
        "-mcmodel=medany", "-ffreestanding", "-nostdlib", "-fno-common",
        "-march=rv64gc", "-fno-stack-protector", "-fno-pie", "-Ikernel",
        f"-DTEST_CASE={case}", "-c", str(source), "-o", str(obj),
    ], check=True)
    objects = ["entry", "start", "console", "printf", "userimg",
               "trampoline_link", "boot_vm", "kernel_trap_entry", "syscall", "proc"]
    subprocess.run(["riscv64-unknown-elf-ld", "-T", "kernel/kernel.ld", "-o",
                    str(kernel)] + [f"kernel/{name}.o" for name in objects] + [str(obj)],
                   check=True)
    symbols = {}
    for line in subprocess.check_output(
        ["riscv64-unknown-elf-nm", str(kernel)], text=True
    ).splitlines():
        parts = line.split()
        if len(parts) == 3:
            symbols[parts[2]] = int(parts[0], 16)
    serial = directory / f"serial{case}.txt"
    monitor = directory / f"monitor{case}.sock"
    traps = directory / f"traps{case}.txt"
    messages = ["TRAP-PREPARE READY\n",
                "unexpected user trap: scause=2 sepc=1000 stval=dead\n",
                "user external interrupt not connected yet: scause=8000000000000009 sepc=1000 stval=dead\n",
                "usertrap called from supervisor mode: scause=8 sepc=1000 stval=dead\n"]
    expected_output = b"".join(bytes([byte]) + b"." for byte in messages[case].encode())
    process = subprocess.Popen([
        "qemu-system-riscv64", "-machine", "virt", "-bios", "none",
        "-kernel", str(kernel), "-display", "none", "-serial", "file:" + str(serial),
        "-monitor", "unix:" + str(monitor) + ",server,nowait",
        "-d", "int", "-D", str(traps),
    ], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        deadline = time.monotonic() + 10
        while not serial.exists() or serial.stat().st_size < len(expected_output):
            if process.poll() is not None:
                raise RuntimeError(process.stderr.read().decode())
            if time.monotonic() > deadline:
                output = serial.read_bytes() if serial.exists() else b""
                log = traps.read_text() if traps.exists() else ""
                raise RuntimeError(f"case {case}: output missing: {output!r}; traps: {log[:1200]}")
            time.sleep(0.05)
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(3)
            connection.connect(str(monitor))

            def receive():
                data = b""
                while b"(qemu) " not in data:
                    chunk = connection.recv(65536)
                    if not chunk:
                        raise RuntimeError("QEMU monitor closed")
                    data += chunk
                return data.decode(errors="replace")

            receive()

            def command(value):
                connection.sendall(value.encode() + b"\n")
                return receive()

            command("stop")
            if serial.read_bytes() != expected_output or traps.read_bytes():
                raise RuntimeError(f"case {case}: output mismatch or real unexpected exception")
            if case:
                # The error path must halt without advancing epc or changing a0.
                memory = command("x /15gx 0x3fffffe000")
            else:
                memory = command(f"x /6gx 0x{symbols['observation']:x}")
                registers = command("info registers")
        values = []
        for line in memory.splitlines():
            match = re.match(r"^[0-9a-fA-F]+:\s+(.*)", line)
            if match:
                values.extend(int(v, 16) for v in re.findall(r"0x[0-9a-fA-F]+", match[1]))
        if case:
            if values[3] != (0 if case == 3 else 0x1000) or values[14] != 123:
                raise RuntimeError("fatal trap modified return address or result")
            print(f"PASS: {messages[case].strip()}; halted without advancing epc")
            return
        satp = 0x8000000000000000 | (symbols["root"] >> 12)
        if values != [0x1004, 0xffffffffffffffff, 0x1000, 456, 999, satp]:
            raise RuntimeError(f"ecall observation mismatch: {values!r}")
        for name, expected in [
            ("sepc", 0x1004),
            ("stvec", 0x3ffffff000 + symbols["uservec"] - symbols["trampoline"]),
            ("satp", satp),
        ]:
            match = re.search(rf"\b{name}\s+([0-9a-fA-F]+)", registers)
            if not match or int(match[1], 16) != expected:
                raise RuntimeError(f"incorrect CPU {name}")
        status = re.search(r"\bsstatus\s+([0-9a-fA-F]+)", registers)
        # Some QEMU versions print only mstatus; these S-mode bits are shared.
        if not status:
            status = re.search(r"\bmstatus\s+([0-9a-fA-F]+)", registers)
        if not status or int(status[1], 16) & ((1 << 18) | 0x122) != ((1 << 18) | 0x20):
            raise RuntimeError("SPP/SIE/SPIE/SUM preparation is incorrect")
        print("PASS: simulated user ecall: epc 0x1000 -> 0x1004; a0=-1; a1/a7 preserved")
        print("PASS: sepc=0x1004; stvec=TRAMPOLINE+uservec offset; satp unchanged")
        print("PASS: SPP=0, SIE=0, SPIE=1; unrelated SUM bit preserved")
    finally:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        process.stderr.close()


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="lab2-prepare-") as directory:
        for case in range(4):
            run_case(pathlib.Path(directory), case)
    print("NOTE: tests simulate CSR state in S-mode; no real U-mode ecall/sret was executed")
