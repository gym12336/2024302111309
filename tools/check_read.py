#!/usr/bin/env python3
"""Real U-mode read calls, invalid arguments and UART-backed waiting in both modes."""
import pathlib
import re
import socket
import subprocess
import tempfile
import time


def run_case(folder, mode):
    main_source = folder / "main.c"
    main_source.write_text(r'''
#include "types.h"
#include "riscv.h"
#include "trap.h"
#include "uart.h"
#include "plic.h"
#include "console.h"
extern void boot_vm_init(void);
extern void user_probe_launch(void) __attribute__((noreturn));
void main(void) {
  boot_vm_init(); trap_init(); uart_init(); plic_init(); w_sie(SIE_SEIE);
  console_input('A'); console_input('B'); console_input(0); console_input('\n');
  user_probe_launch();
}
''')
    console_source = folder / "console_wrapper.c"
    console_source.write_text('#include "course_sid.h"\n#undef LAB2_BUF_SEMANTICS\n'
                              '#define LAB2_BUF_SEMANTICS TEST_MODE\n#include "console.c"\n')
    probe_source = folder / "probe.S"
    requests = [(0, 0, 0), (1, 0x3000, 1), (0, 0x1000, 1), (0, 0x3fffffe000, 1),
                (0, 0, 1), (0, 0x3fff, 2), (0, 0x3000, -1), (0, 0x3fffffffff, 2)]
    calls = "\n".join(f"li a0, {fd}\nli a1, {address}\nli a2, {size}\nli a7, 5\necall\nsd a0, {i * 8}(s0)"
                      for i, (fd, address, size) in enumerate(requests))
    probe_source.write_text(f'''
    .section .rodata.user_probe,"a"
    .option norvc
    .option norelax
    .balign 4
    .globl user_probe_start, user_probe_end, read_wait, read_done, read_last
user_probe_start:
    li s0, 0x3e00
    li s3, 0x12345678
    li t2, 0xabcdef
    li a3, 0x55aa
{calls}
    li a7, 11
    ecall
    sd a0, 64(s0)
    li a0, 0
    li a1, 0x3000
    li a2, 64
    li a7, 5
    ecall
    sd a0, 72(s0)
    li t0, 0x3ff8
    li t1, 1
    sd t1, 0(t0)
    li a0, 0
    li a1, 0x3040
    li a2, 64
    li a7, 5
read_wait:
    ecall
    sd a0, 80(s0)
    li a7, 11
read_last:
    ecall
    sd a0, 88(s0)
    li t1, 0x50415353
    sd t1, 0(t0)
read_done:
    j read_done
user_probe_end:
''')
    flags = ["-Wall", "-Werror", "-O", "-std=gnu99", "-mcmodel=medany", "-ffreestanding",
             "-nostdlib", "-fno-common", "-march=rv64gc", "-fno-stack-protector", "-fno-pie", "-Ikernel"]
    for source, name in ((main_source, "main"), (console_source, "console"), (probe_source, "probe")):
        subprocess.run(["riscv64-unknown-elf-gcc"] + flags + [f"-DTEST_MODE={mode}", "-c",
                       str(source), "-o", str(folder / (name + ".o"))], check=True)
    kernel = folder / "kernel.elf"
    objects = "entry start printf userimg trampoline_link boot_vm trap kernel_trap_entry proc syscall user_mem plic user_boot".split()
    subprocess.run(["riscv64-unknown-elf-ld", "-T", "kernel/kernel.ld", "-o", str(kernel)] +
                   [f"kernel/{name}.o" for name in objects] + [str(folder / (name + ".o")) for name in ("main", "console", "probe")], check=True)
    symbols = {}
    for line in subprocess.check_output(["riscv64-unknown-elf-nm", str(kernel)], text=True).splitlines():
        parts = line.split()
        if len(parts) == 3:
            symbols[parts[2]] = int(parts[0], 16)
    uart, monitor, traps = [folder / name for name in ("uart.sock", "monitor.sock", "traps")]
    process = subprocess.Popen([
        "qemu-system-riscv64", "-machine", "virt", "-bios", "none", "-kernel", str(kernel), "-S",
        "-display", "none", "-chardev", f"socket,id=uart,path={uart},server=on,wait=off",
        "-serial", "chardev:uart", "-monitor", f"unix:{monitor},server,nowait", "-d", "int", "-D", str(traps),
    ], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        deadline = time.monotonic() + 10
        while not uart.exists() or not monitor.exists():
            if process.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError("QEMU did not start")
            time.sleep(0.02)
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as control, socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as serial:
            control.settimeout(3); control.connect(str(monitor))
            serial.settimeout(3); serial.connect(str(uart))

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
                    raise RuntimeError("monitor memory read failed")
                return values

            def register(name):
                output = command("info registers")
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
                        raise RuntimeError("read timeout: " + traps.read_text()[:1800])
                    command("cont")
                    time.sleep(0.02)

            stack = symbols["probe_stack"]
            wait_epc = 0x1000 + symbols["read_wait"] - symbols["user_probe_start"]
            wait_stopped(lambda: memory(stack + 0xff8) == [1]
                         and memory(symbols["boot_trapframe"] + 24) == [wait_epc + 4]
                         and register("satp") == (1 << 63) | (symbols["root"] >> 12))
            if memory(stack + 0xe00, 10) != [0] + [(1 << 64) - 1] * 7 + [1, 4]:
                raise RuntimeError("bad read arguments consumed data or returned incorrect results")
            if memory(stack, 5, "b") != [65, 66, 0, 10, 0] or memory(symbols["input"] + 64, 4) != [4, 4, 4, 0]:
                raise RuntimeError("queued read data, boundary or counters incorrect")
            if register("stvec") != symbols["kernel_trap_entry"]:
                raise RuntimeError("waiting read has wrong interrupt entry")
            command("cont"); time.sleep(0.1); command("stop")
            if memory(stack + 0xff8) != [1]:
                raise RuntimeError("empty read returned before input")
            serial.sendall(b"Z")
            if mode == 0:
                command("cont")
                wait_stopped(lambda: memory(symbols["uart_rx_count"]) == [1])
                if memory(stack + 0xff8) != [1] or memory(symbols["input"] + 64, 4) != [4, 4, 5, 0]:
                    raise RuntimeError("line read returned before newline")
                serial.sendall(b"\n")
            command("cont")
            done_pc = 0x1000 + symbols["read_done"] - symbols["user_probe_start"]
            wait_stopped(lambda: memory(stack + 0xff8) == [0x50415353] and register("pc") == done_pc)
            expected = b"Z" if mode == 1 else b"Z\n"
            if memory(stack + 0xe50, 2) != [len(expected), 1]:
                raise RuntimeError("waiting read count or subsequent getpid incorrect")
            if memory(stack + 0x40, len(expected) + 1, "b") != list(expected) + [0]:
                raise RuntimeError("UART read buffer or surrounding byte incorrect")
            if memory(symbols["input"] + 64, 4) != [4 + len(expected)] * 3 + [0]:
                raise RuntimeError("queue not consumed exactly")
            for name, value in (("x4/tp", 0x104), ("x7/t2", 0xabcdef), ("x13/a3", 0x55aa), ("x19/s3", 0x12345678), ("x2/sp", 0x4000)):
                if register(name) != value:
                    raise RuntimeError("nested kernel interrupt damaged user register " + name)
            if register("satp") != (1 << 63) | (symbols["user_root"] >> 12):
                raise RuntimeError("read failed to return to user page table")
            frame = memory(symbols["boot_trapframe"], 36)
            final_epc = 0x1000 + symbols["read_last"] - symbols["user_probe_start"] + 4
            if frame[3] != final_epc or frame[14] != 1 or frame[21] != 11:
                raise RuntimeError("kernel IRQ corrupted saved user epc or call result")
            echoed = b""
            while len(echoed) < 4 + len(expected):
                chunk = serial.recv(4 + len(expected) - len(echoed))
                if not chunk:
                    raise RuntimeError("serial closed before expected echo")
                echoed += chunk
            if echoed != b"AB\0\n" + expected:
                raise RuntimeError("raw echo incorrect")
        events = [line for line in traps.read_text().splitlines() if line.strip()]
        ecalls = [line for line in events if "desc=user_ecall" in line]
        external = [line for line in events if "desc=s_external" in line]
        if len(ecalls) != 12 or len(events) != len(ecalls) + len(external) or not external:
            raise RuntimeError("unexpected real hardware trap sequence")
        if any(int(re.search(r"epc:0x([0-9a-fA-F]+)", line)[1], 16) < 0x80000000 for line in external):
            raise RuntimeError("expected UART interrupt while waiting inside S-mode read")
        name = "stream" if mode == 1 else "line"
        print(f"PASS: {name} read: 12 real U-mode ecalls; bad fd/pointer/permission/length rejected without consuming input")
        print(f"PASS: {name} read: zero length and queued 4-byte NUL-containing partial read; destination bounds correct")
        print(f"PASS: {name} read: empty request waits; real S-mode UART IRQ resumes it; returns {len(expected)} byte(s)")
        print(f"PASS: {name} read: user registers/epc/page table restored; getpid continues; raw echo exact")
        if mode == 0:
            print("PASS: line read remains waiting after Z and returns Z/newline only after newline arrives")
    finally:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill(); process.wait()
        process.stderr.close()


if __name__ == "__main__":
    for mode in (1, 0):
        with tempfile.TemporaryDirectory(prefix="lab2-read-") as folder:
            run_case(pathlib.Path(folder), mode)
