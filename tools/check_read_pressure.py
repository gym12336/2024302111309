#!/usr/bin/env python3
"""Fill the ring using actual UART input before real U-mode read calls."""
import pathlib
import re
import socket
import subprocess
import tempfile
import time


def run_case(folder, mode):
    main_source = folder / "main.c"
    main_source.write_text(r'''
#include "user_boot.c"
#include "uart.h"
#include "plic.h"
extern void boot_vm_init(void);
void read_test_release(uint64 stage) {
  *(volatile uint64 *)(probe_stack + 0xff0) = stage;
}
void main(void) {
  boot_vm_init(); trap_init(); uart_init(); plic_init(); w_sie(SIE_SEIE);
  user_probe_launch();
}
''')
    # Observe completed reception to release the test user's read gate.
    # Production queue/read/IRQ code is included unchanged; only the gate is added.
    wrapper = folder / "console_wrapper.c"
    wrapper.write_text(r'''
#include "course_sid.h"
#undef LAB2_BUF_SEMANTICS
#define LAB2_BUF_SEMANTICS TEST_MODE
#define uartintr production_uartintr
#include "console.c"
#undef uartintr
extern void read_test_release(uint64);
void uartintr(void) {
  production_uartintr();
  if (uart_rx_count >= 88) read_test_release(3);
  else if (uart_rx_count >= 86) read_test_release(2);
  else if (uart_rx_count >= 80) read_test_release(1);
}
''')
    probe = folder / "probe.S"
    probe.write_text(r'''
    .section .rodata.user_probe,"a"
    .option norvc
    .option norelax
    .balign 4
    .globl user_probe_start, user_probe_end, pressure_done, pressure_last
user_probe_start:
    li s0, 0x3e00
    li s3, 0x12345678
    li t2, 0xabcdef
    li a3, 0x55aa
    li t0, 0x3000
    li t1, 0xa5
    sb t1, 0(t0)
    sb t1, 128(t0)
    li t1, 0x5a
    sb t1, 65(t0)
    sb t1, 135(t0)
    li t0, 0x3ff0
wait_one:
    ld t1, 0(t0)
    li t3, 1
    bltu t1, t3, wait_one
    li a0, 0
    li a1, 0x3001
    li a2, 64
    li a7, 5
    ecall
    sd a0, 0(s0)
    li a7, 11
    ecall
    sd a0, 8(s0)
    li t1, 1
    sd t1, 8(t0)
wait_two:
    ld t1, 0(t0)
    li t3, 2
    bltu t1, t3, wait_two
    li a0, 0
    li a1, 0x3081
    li a2, 64
    li a7, 5
    ecall
    sd a0, 16(s0)
#if TEST_MODE == 0
    li a0, 0
    li a1, 0x30c1
    li a2, 64
    li a7, 5
    ecall
    sd a0, 24(s0)
#endif
    li t1, 2
    sd t1, 8(t0)
wait_three:
    ld t1, 0(t0)
    li t3, 3
    bltu t1, t3, wait_three
    li a0, 0
    li a1, 0x3101
    li a2, 64
    li a7, 5
    ecall
    sd a0, 32(s0)
    li a7, 11
pressure_last:
    ecall
    sd a0, 40(s0)
    li t1, 0x50415353
    sd t1, 8(t0)
pressure_done:
    j pressure_done
user_probe_end:
''')
    flags = ["-Wall", "-Werror", "-O", "-std=gnu99", "-mcmodel=medany", "-ffreestanding",
             "-nostdlib", "-fno-common", "-march=rv64gc", "-fno-stack-protector", "-fno-pie", "-Ikernel"]
    for source, name in ((main_source, "main"), (wrapper, "console"), (probe, "probe")):
        subprocess.run(["riscv64-unknown-elf-gcc"] + flags + [f"-DTEST_MODE={mode}", "-c", str(source), "-o", str(folder / (name + ".o"))], check=True)
    kernel = folder / "kernel.elf"
    objects = "entry start printf userimg trampoline_link boot_vm trap kernel_trap_entry proc syscall user_mem plic".split()
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
        deadline = time.monotonic() + 15
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
                    part = control.recv(65536)
                    if not part:
                        raise RuntimeError("monitor closed")
                    data += part
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
                        raise RuntimeError("pressure timeout: " + traps.read_text()[:1800])
                    command("cont"); time.sleep(0.02)

            stack = symbols["probe_stack"]
            user_satp = (1 << 63) | (symbols["user_root"] >> 12)
            wait_stopped(lambda: register("satp") == user_satp)
            payload = bytes(range(0x20, 0x60))
            serial.sendall(payload + b"abcdefghijklmnop")
            command("cont")
            wait_stopped(lambda: memory(stack + 0xff8) == [1] and register("satp") == user_satp)
            if memory(stack + 1, 64, "b") != list(payload) or memory(stack, width="b") != [0xa5] or memory(stack + 65, width="b") != [0x5a]:
                raise RuntimeError("64-byte read content or destination guards incorrect")
            if memory(stack + 0xe00, 2) != [64, 1] or memory(symbols["input"] + 64, 4) != [64, 64, 64, 16]:
                raise RuntimeError("capacity read count, consumption or drop policy incorrect")
            if memory(symbols["uart_rx_count"]) != [80]:
                raise RuntimeError("not all 80 UART bytes were drained")
            serial.sendall(b"AB\nCD\n")
            command("cont")
            wait_stopped(lambda: memory(stack + 0xff8) == [2] and register("satp") == user_satp)
            if mode == 1:
                expected_results, first = [6, 0], b"AB\nCD\n"
            else:
                expected_results, first = [3, 3], b"AB\n"
                if memory(stack + 0xc1, 4, "b") != list(b"CD\n") + [0]:
                    raise RuntimeError("second line was lost or merged")
            if memory(stack + 0xe10, 2) != expected_results or memory(stack + 0x81, len(first), "b") != list(first):
                raise RuntimeError("line boundary or stream batch incorrect")
            if memory(stack + 0x80, width="b") != [0xa5] or memory(stack + 0x87, width="b") != [0x5a]:
                raise RuntimeError("second read wrote outside its result")
            if memory(symbols["input"] + 64, 4) != [70, 70, 70, 16]:
                raise RuntimeError("slot reuse after draining failed")
            serial.sendall(b"Z\n")
            command("cont")
            done_pc = 0x1000 + symbols["pressure_done"] - symbols["user_probe_start"]
            wait_stopped(lambda: memory(stack + 0xff8) == [0x50415353] and register("pc") == done_pc)
            if memory(stack + 0xe20, 2) != [2, 1] or memory(stack + 0x101, 3, "b") != list(b"Z\n") + [0]:
                raise RuntimeError("post-overflow input or getpid failed")
            if memory(symbols["input"] + 64, 4) != [72, 72, 72, 16] or memory(symbols["uart_rx_count"]) != [88]:
                raise RuntimeError("final accepted/received/dropped accounting incorrect")
            for name, expected in (("x2/sp", 0x4000), ("x4/tp", 0x104), ("x7/t2", 0xabcdef), ("x13/a3", 0x55aa), ("x19/s3", 0x12345678)):
                if register(name) != expected:
                    raise RuntimeError("user register changed during pressure: " + name)
            irqs = memory(symbols["uart_irq_count"])[0]
            command("cont"); time.sleep(0.1); command("stop")
            if memory(symbols["uart_irq_count"]) != [irqs]:
                raise RuntimeError("interrupt storm after input drained")
            expected_echo = payload + b"AB\nCD\nZ\n"
            echoed = b""
            while len(echoed) < len(expected_echo):
                part = serial.recv(len(expected_echo) - len(echoed))
                if not part:
                    raise RuntimeError("serial closed")
                echoed += part
            if echoed != expected_echo:
                raise RuntimeError("dropped input was echoed or accepted input was corrupted")
            serial.settimeout(0.1)
            try:
                extra = serial.recv(1)
            except socket.timeout:
                extra = b""
            if extra:
                raise RuntimeError("extra echo or diagnostic")
        events = [line for line in traps.read_text().splitlines() if line.strip()]
        ecalls = [line for line in events if "desc=user_ecall" in line]
        external = [line for line in events if "desc=s_external" in line]
        if len(ecalls) != (5 if mode == 1 else 6) or len(external) != irqs or len(events) != len(ecalls) + len(external):
            raise RuntimeError("unexpected pressure trap sequence")
        name = "stream" if mode == 1 else "line"
        print(f"PASS: {name} pressure: UART receives 80 bytes; keeps 64, drops 16; real user read returns 64 with intact guards")
        print(f"PASS: {name} pressure: drain then reuse; 88 received = 72 accepted + 16 dropped; FIFO and raw echo correct")
        print(f"PASS: {name} pressure: AB/newline/CD/newline returns {'6 once' if mode == 1 else '3 then 3'}; Z/newline and getpid continue")
        print(f"PASS: {name} pressure: user registers preserved; no unexpected trap or post-input IRQ storm")
    finally:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill(); process.wait()
        process.stderr.close()


if __name__ == "__main__":
    for mode in (1, 0):
        with tempfile.TemporaryDirectory(prefix="lab2-read-pressure-") as folder:
            run_case(pathlib.Path(folder), mode)
