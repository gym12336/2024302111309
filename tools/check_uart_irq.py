#!/usr/bin/env python3
"""Inject actual UART bytes into isolated S-mode and U-mode probe kernels."""
import pathlib
import re
import socket
import subprocess
import tempfile
import time

from check_kernel_irq import REGS


def run_case(folder, user):
    source = folder / "main.c"
    source.write_text('''
#include "trapframe.h"
#include "riscv.h"
#include "memlayout.h"
#include "trap.h"
#include "uart.h"
#include "plic.h"
extern void boot_vm_init(void);
extern void user_probe_launch(void) __attribute__((noreturn));
extern void uart_probe(void) __attribute__((noreturn));
void main(void)
{
  boot_vm_init();
  trap_init();
  uart_init();
  plic_init();
  w_sie(SIE_SEIE);
#if USER_PROBE
  user_probe_launch();
#else
  for (uint64 i = 0; i < 36; i++)
    *(uint64 *)((uint8 *)TRAPFRAME + i * 8) = 0x9000 + i;
  uart_probe();
#endif
}
''')
    probe = folder / "probe.S"
    loads = "\n".join(f"    li {reg}, {0 if reg == 'tp' else 0x301 + i}" for i, reg in enumerate(REGS) if reg != "sp")
    probe.write_text(f'''
    .section .text
    .option norvc
    .option norelax
    .globl uart_probe, uart_probe_loop, user_probe_start, user_probe_end
uart_probe:
    la sp, uart_probe_stack_top
{loads}
    csrsi sstatus, 2
uart_probe_loop:
    j uart_probe_loop
user_probe_start:
    j user_probe_start
user_probe_end:
    .section .bss
    .balign 16
uart_probe_stack:
    .space 8192
    .globl uart_probe_stack_top
uart_probe_stack_top:
''')
    flags = ["-Wall", "-Werror", "-O", "-std=gnu99", "-mcmodel=medany", "-ffreestanding",
             "-nostdlib", "-fno-common", "-march=rv64gc", "-fno-stack-protector", "-fno-pie", "-Ikernel"]
    for item, name in ((source, "main"), (probe, "probe")):
        subprocess.run(["riscv64-unknown-elf-gcc"] + flags + [f"-DUSER_PROBE={int(user)}", "-c",
                       str(item), "-o", str(folder / (name + ".o"))], check=True)
    kernel = folder / "kernel.elf"
    objects = "entry start console printf userimg trampoline_link boot_vm trap kernel_trap_entry proc syscall user_mem plic user_boot".split()
    subprocess.run(["riscv64-unknown-elf-ld", "-T", "kernel/kernel.ld", "-o", str(kernel)] +
                   [f"kernel/{name}.o" for name in objects] + [str(folder / "main.o"), str(folder / "probe.o")], check=True)
    symbols = {}
    for line in subprocess.check_output(["riscv64-unknown-elf-nm", str(kernel)], text=True).splitlines():
        parts = line.split()
        if len(parts) == 3:
            symbols[parts[2]] = int(parts[0], 16)
    monitor, uart, traps = [folder / name for name in ("monitor.sock", "uart.sock", "traps")]
    process = subprocess.Popen([
        "qemu-system-riscv64", "-machine", "virt", "-bios", "none", "-kernel", str(kernel),
        "-display", "none", "-chardev", f"socket,id=uart,path={uart},server=on,wait=off",
        "-serial", "chardev:uart", "-monitor", f"unix:{monitor},server,nowait", "-d", "int", "-D", str(traps),
    ], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        deadline = time.monotonic() + 10
        while not monitor.exists() or not uart.exists():
            if process.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError("QEMU did not start")
            time.sleep(0.02)
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as control, socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as serial:
            control.settimeout(3)
            control.connect(str(monitor))
            serial.settimeout(3)
            serial.connect(str(uart))

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

            def memory(address, count=1, width="g"):
                values = []
                for line in command(f"xp /{count}{width}x 0x{address:x}").splitlines():
                    match = re.match(r"^[0-9a-fA-F]+:\s+(.*)", line)
                    if match:
                        values.extend(int(v, 16) for v in re.findall(r"0x[0-9a-fA-F]+", match[1]))
                if len(values) != count:
                    raise RuntimeError("memory read failed")
                return values

            def register(output, name):
                match = re.search(r"\b" + re.escape(name) + r"\s+([0-9a-fA-F]+)", output)
                if not match:
                    raise RuntimeError("missing register " + name)
                return int(match[1], 16)

            def wait_stopped(predicate):
                while True:
                    command("stop")
                    if predicate():
                        return
                    if time.monotonic() > deadline:
                        raise RuntimeError("probe timeout: " + traps.read_text()[:2000])
                    command("cont")
                    time.sleep(0.02)

            target = 0x1000 if user else symbols["uart_probe_loop"]
            expected_satp = (1 << 63) | (symbols["user_root" if user else "root"] >> 12)

            def at_probe():
                registers = command("info registers")
                return register(registers, "pc") == target and register(registers, "satp") == expected_satp

            # QEMU boot ROM also starts at physical 0x1000; PC alone is ambiguous.
            wait_stopped(at_probe)
            baseline_frame = memory(symbols["boot_trapframe"], 36)
            initial = command("info registers")
            if memory(0x10000001, width="b") != [1] or memory(0x10000003, width="b") != [3]:
                raise RuntimeError("UART RX-only or 8N1 configuration failed")
            if (memory(0x0c000028, width="w") != [1] or memory(0x0c002080, width="w") != [1 << 10]
                    or memory(0x0c201000, width="w") != [0] or register(initial, "mie") & 0x200 == 0):
                raise RuntimeError("PLIC priority/enable/threshold or SEIE incorrect")
            received = b""
            previous_irqs = 0
            for chunk in (b"A", b"b\x00\n", b"Z"):
                serial.sendall(chunk)
                expected_size = len(received) + len(chunk)
                command("cont")
                wait_stopped(lambda: memory(symbols["uart_rx_count"])[0] == expected_size
                             and register(command("info registers"), "pc") == target)
                echoed = b""
                while len(echoed) < len(chunk):
                    part = serial.recv(len(chunk) - len(echoed))
                    if not part:
                        raise RuntimeError("serial closed")
                    echoed += part
                if echoed != chunk:
                    raise RuntimeError(f"raw echo mismatch: {echoed!r}")
                received += echoed
                current = command("info registers")
                for i, reg in enumerate(REGS, 1):
                    name = f"x{i}/{reg}"
                    if register(current, name) != register(initial, name):
                        raise RuntimeError("register was not restored: " + reg)
                if register(current, "satp") != register(initial, "satp"):
                    raise RuntimeError("page table not restored")
                if memory(symbols["boot_trapframe"], 36) != baseline_frame:
                    raise RuntimeError("user trapframe changed")
                irqs = memory(symbols["uart_irq_count"])[0]
                if irqs <= previous_irqs or memory(0x0c001000, width="w")[0] & (1 << 10) or register(current, "mip") & 0x200:
                    raise RuntimeError("IRQ not consumed or PLIC completion failed")
                previous_irqs = irqs
            command("cont")
            time.sleep(0.1)
            command("stop")
            if memory(symbols["uart_irq_count"])[0] != previous_irqs:
                raise RuntimeError("interrupt storm after FIFO drained")
            serial.settimeout(0.1)
            try:
                extra = serial.recv(1)
            except socket.timeout:
                extra = b""
            if extra:
                raise RuntimeError("extra serial output")
            # This student's production configuration is a 64-byte stream ring.
            if memory(symbols["input"], 5, "b") != list(received):
                raise RuntimeError("UART bytes were echoed but not buffered")
            if memory(symbols["input"] + 64, 4) != [0, 5, 5, 0]:
                raise RuntimeError("stream ring indices or drop count incorrect")
        events = [line for line in traps.read_text().splitlines() if line.strip()]
        if len(events) != previous_irqs or any("desc=s_external" not in line for line in events):
            raise RuntimeError("unexpected hardware trap sequence")
        mode = "U" if user else "S"
        print(f"PASS: {mode}-mode UART IRQ10 receives and echoes 5 raw bytes: A, b, NUL, newline, Z")
        print(f"PASS: {mode}-mode restores all 31 registers, satp and return PC; user frame unchanged")
        print(f"PASS: {mode}-mode {previous_irqs} real external interrupts; repeated delivery and completion; no IRQ storm")
        print(f"PASS: {mode}-mode all 5 UART bytes buffered in order; r=0, w=e=5, dropped=0")
    finally:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        process.stderr.close()


if __name__ == "__main__":
    for user in (False, True):
        with tempfile.TemporaryDirectory(prefix="lab2-uart-") as folder:
            run_case(pathlib.Path(folder), user)
