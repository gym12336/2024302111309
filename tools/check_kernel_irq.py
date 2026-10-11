#!/usr/bin/env python3
"""Run an isolated real S-mode software interrupt and a fatal kernel fault."""
import pathlib
import re
import socket
import subprocess
import tempfile
import time

REGS = "ra sp gp tp t0 t1 t2 s0 s1 a0 a1 a2 a3 a4 a5 a6 a7 s2 s3 s4 s5 s6 s7 s8 s9 s10 s11 t3 t4 t5 t6".split()


def run_case(folder, fault):
    main_source = folder / "main.c"
    main_source.write_text('''
#include "trapframe.h"
#include "riscv.h"
#include "memlayout.h"
#include "trap.h"
extern void boot_vm_init(void);
extern void kernel_irq_probe(void) __attribute__((noreturn));
void main(void)
{
  boot_vm_init();
  trap_init();
  for (uint64 i = 0; i < 36; i++)
    *(uint64 *)((uint8 *)TRAPFRAME + i * 8) = 0x9000 + i;
  kernel_irq_probe();
}
''')
    probe_source = folder / "probe.S"
    loads = "\n".join(f"    li {reg}, 0x{0x201 + i:x}" for i, reg in enumerate(REGS) if reg != "sp")
    stores = "\n".join(f"    sd {reg}, {i * 8 - 256}(sp)" for i, reg in enumerate(REGS))
    probe_source.write_text(f'''
    .section .text
    .option norvc
    .option norelax
    .globl kernel_irq_probe, irq_probe_resume, irq_probe_done, irq_probe_done_end, irq_probe_fault
kernel_irq_probe:
    la sp, irq_probe_stack_top
#if FAULT
irq_probe_fault:
    .word 0
#else
irq_probe_fault:
    csrwi sie, 2
    csrsi sip, 2
{loads}
    csrsi sstatus, 2
irq_probe_resume:
{stores}
    csrci sstatus, 2
    csrr t1, sip
    sd t1, -264(sp)
    li t1, 0x50415353
    sd t1, -8(sp)
#endif
#if FAULT
irq_probe_resume:
#endif
irq_probe_done:
    wfi
    j irq_probe_done
irq_probe_done_end:
    .section .bss
    .balign 16
    .globl irq_probe_stack, irq_probe_stack_top
irq_probe_stack:
    .space 8192
irq_probe_stack_top:
''')
    flags = ["-Wall", "-Werror", "-O", "-std=gnu99", "-mcmodel=medany", "-ffreestanding",
             "-nostdlib", "-fno-common", "-march=rv64gc", "-fno-stack-protector", "-fno-pie", "-Ikernel"]
    for source, name in ((main_source, "main"), (probe_source, "probe")):
        subprocess.run(["riscv64-unknown-elf-gcc"] + flags + [f"-DFAULT={int(fault)}", "-c",
                       str(source), "-o", str(folder / (name + ".o"))], check=True)
    kernel = folder / "kernel.elf"
    objects = "entry start console printf userimg trampoline_link boot_vm trap kernel_trap_entry proc syscall user_mem plic".split()
    subprocess.run(["riscv64-unknown-elf-ld", "-T", "kernel/kernel.ld", "-o", str(kernel)] +
                   [f"kernel/{name}.o" for name in objects] + [str(folder / "main.o"), str(folder / "probe.o")], check=True)
    symbols = {}
    for line in subprocess.check_output(["riscv64-unknown-elf-nm", str(kernel)], text=True).splitlines():
        parts = line.split()
        if len(parts) == 3:
            symbols[parts[2]] = int(parts[0], 16)
    monitor, serial, traps = [folder / name for name in ("monitor.sock", "serial", "traps")]
    fault_message = f"unexpected kernel trap: scause=2 sepc={symbols['irq_probe_fault']:x} stval=0\n"
    fault_output = b"".join(bytes([byte]) + b"." for byte in fault_message.encode())
    process = subprocess.Popen([
        "qemu-system-riscv64", "-machine", "virt", "-bios", "none", "-kernel", str(kernel),
        "-display", "none", "-serial", "file:" + str(serial),
        "-monitor", "unix:" + str(monitor) + ",server,nowait", "-d", "int", "-D", str(traps),
    ], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        deadline = time.monotonic() + 10
        while not monitor.exists():
            if process.poll() is not None:
                raise RuntimeError(process.stderr.read().decode())
            if time.monotonic() > deadline:
                raise RuntimeError("monitor did not start")
            time.sleep(0.05)
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(3)
            connection.connect(str(monitor))

            def receive():
                data = b""
                while b"(qemu) " not in data:
                    chunk = connection.recv(65536)
                    if not chunk:
                        raise RuntimeError("monitor closed")
                    data += chunk
                return data.decode(errors="replace")

            receive()

            def command(value):
                connection.sendall(value.encode() + b"\n")
                return receive()

            def memory(address, count):
                values = []
                for line in command(f"xp /{count}gx 0x{address:x}").splitlines():
                    match = re.match(r"^[0-9a-fA-F]+:\s+(.*)", line)
                    if match:
                        values.extend(int(v, 16) for v in re.findall(r"0x[0-9a-fA-F]+", match[1]))
                if len(values) != count:
                    raise RuntimeError("memory read failed")
                return values

            while True:
                command("stop")
                if fault:
                    ready = serial.exists() and serial.stat().st_size >= len(fault_output)
                else:
                    ready = memory(symbols["irq_probe_stack_top"] - 8, 1) == [0x50415353]
                if ready:
                    break
                if time.monotonic() > deadline:
                    raise RuntimeError("kernel probe did not finish: " + traps.read_text()[:1500])
                command("cont")
                time.sleep(0.05)
            registers = command("info registers")
            count = memory(symbols["kernel_softirq_count"], 1)[0]
            frame = memory(symbols["boot_trapframe"], 36)
            snapshot = memory(symbols["irq_probe_stack_top"] - 256, 31)
            pending = memory(symbols["irq_probe_stack_top"] - 264, 1)[0]

        def register(name):
            match = re.search(r"\b" + re.escape(name) + r"\s+([0-9a-fA-F]+)", registers)
            if not match:
                raise RuntimeError(f"missing register {name}")
            return int(match[1], 16)

        if frame != [0x9000 + i for i in range(36)]:
            raise RuntimeError("kernel trap overwrote the user trapframe")
        if register("satp") != 0x8000000000000000 | (symbols["root"] >> 12):
            raise RuntimeError("kernel page table changed")
        events = [line for line in traps.read_text().splitlines() if line.strip()]
        if fault:
            if serial.read_bytes() != fault_output or count or register("sepc") != symbols["irq_probe_fault"]:
                raise RuntimeError("fatal kernel exception was not diagnosed accurately")
            if len(events) != 1 or "illegal_instruction" not in events[0]:
                raise RuntimeError("expected exactly one real illegal-instruction exception")
            print("PASS: real S-mode illegal instruction is diagnosed and halted; user frame unchanged")
            return
        expected = [0x201 + i for i in range(31)]
        expected[1] = symbols["irq_probe_stack_top"]
        if snapshot != expected or count != 1 or pending & 2:
            raise RuntimeError(f"register restoration or SSIP acknowledgement failed: {snapshot!r}, count={count}")
        if register("sepc") != symbols["irq_probe_resume"] or register("x2/sp") != symbols["irq_probe_stack_top"]:
            raise RuntimeError("kernel interrupt skipped its return instruction or changed sp")
        if not symbols["irq_probe_done"] <= register("pc") < symbols["irq_probe_done_end"]:
            raise RuntimeError("kernel did not continue to its final loop")
        if len(events) != 1 or "s_software" not in events[0]:
            raise RuntimeError("expected exactly one real supervisor software interrupt: " + traps.read_text())
        print("PASS: one real S-mode software interrupt; SSIP cleared, handler count=1")
        print("PASS: all 31 kernel registers restored; original sp and sepc preserved")
        print("PASS: kernel continued after sret; satp and all 288 user trapframe bytes unchanged")
        print("TRACE: " + events[0])
    finally:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        process.stderr.close()


if __name__ == "__main__":
    for fault in (False, True):
        with tempfile.TemporaryDirectory(prefix="lab2-kernel-irq-") as folder:
            run_case(pathlib.Path(folder), fault)
