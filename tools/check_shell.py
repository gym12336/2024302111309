#!/usr/bin/env python3
"""Exercise the formal Shell and inspect its real process banks through QEMU."""
import pathlib
import re
import selectors
import socket
import subprocess
import tempfile
import time


def main():
    symbols = {}
    for line in subprocess.check_output(["riscv64-unknown-elf-nm", "kernel/kernel"], text=True).splitlines():
        parts = line.split()
        if len(parts) == 3:
            symbols[parts[2]] = int(parts[0], 16)
    with tempfile.TemporaryDirectory(prefix="lab2-shell-") as directory:
        directory = pathlib.Path(directory)
        monitor, traps = directory / "monitor", directory / "traps"
        process = subprocess.Popen([
            "qemu-system-riscv64", "-machine", "virt", "-bios", "none", "-kernel", "kernel/kernel",
            "-display", "none", "-serial", "stdio", "-monitor",
            f"unix:{monitor},server,nowait", "-d", "int", "-D", str(traps),
        ], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        output = bytearray()
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            def drain(duration=0.05):
                for key, _ in selector.select(duration):
                    import os
                    chunk = os.read(key.fd, 65536)
                    if chunk:
                        output.extend(chunk)
                    elif process.poll() is not None:
                        raise RuntimeError(process.stderr.read().decode())

            def expect(pattern, start=0, timeout=10):
                deadline = time.monotonic() + timeout
                while not re.search(pattern, bytes(output[start:])):
                    if time.monotonic() > deadline:
                        raise RuntimeError(f"missing {pattern!r}: {bytes(output[start:])!r}; {traps.read_text()[-1000:]}")
                    drain()

            expect(rb"sh> ")
            banner = pathlib.Path("expect_banner.txt").read_bytes()
            assert bytes(output) == banner + b"sh> ", "Lab1 prefix changed"
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
                result = command(f"xp /{count}gx 0x{address:x}")
                values = []
                for line in result.splitlines():
                    match = re.match(r"^[0-9a-fA-F]+:\s+(.*)", line)
                    if match:
                        values.extend(int(v, 16) for v in re.findall(r"0x[0-9a-fA-F]+", match[1]))
                assert len(values) == count, result
                return values

            command("stop")
            arena = memory(symbols["arena_base"], 1)[0]
            assert arena == (symbols["kernel_end"] + 4095) & ~4095
            record = memory(symbols["processes"], 10)
            pid, root, state, _, parent, _, base, kstack, frame, image_size = record
            assert (pid, state, parent, base) == (1, 1, 0, arena)
            assert root == arena + 21 * 4096 and kstack == root and frame == arena + 18 * 4096
            assert arena + 104 * 4096 <= 0x88000000
            low = memory(root + 2 * 4096, 19)
            def pte(pa, flags):
                return ((pa >> 12) << 10) | flags
            assert low[0] == pte(arena, 0xdf)
            assert low[16] == 0 and low[17:19] == [pte(arena + 16*4096, 0xd7), pte(arena + 17*4096, 0xd7)]
            assert memory(root + 8, 2) == [0, 0]
            assert memory(root + 4 * 4096 + 510 * 8, 2) == [pte(frame, 0xc7), pte(symbols["trampoline"], 0x4b)]
            tf = memory(frame, 36)
            assert tf[1] == kstack and 0x11000 <= tf[6] <= 0x13000 and tf[6] % 16 == 0
            bss = pathlib.Path("user-flat/sh.bin").stat().st_size
            if image_size > bss:
                words = memory(arena + (bss & ~7), ((image_size + 7) // 8) - (bss // 8))
                raw = b"".join(w.to_bytes(8, "little") for w in words)
                assert not any(raw[bss % 8: image_size - (bss & ~7)])
            print(f"PASS: formal sh PID=1; kernel_end=0x{symbols['kernel_end']:x}; banks start=0x{arena:x}, 104 pages")
            print("PASS: image VA=0, BSS zero; private frame/kernel stack; 16-byte user stack alignment; guard and supervisor mappings")
            command("cont")

            def run(name, pattern):
                start = len(output)
                process.stdin.write(name.encode() + b"\n")
                process.stdin.flush()
                expect(pattern, start)
                expect(rb"sh> ", start)
                return bytes(output[start:])

            run("hi", rb"hi: user program running, pid=2\n")
            run("badecall", rb"TEST-1 PASS: unknown syscalls all return -1\n")
            run("missing", rb"exec missing\n failed\n")
            run("proctest", rb"PROCTEST PASS:.*capacity\n")
            for _ in range(6):
                run("hi", rb"hi: user program running, pid=\d+\n")
            start = len(output)
            process.stdin.write(b"bufstorm\n"); process.stdin.flush()
            deadline = time.monotonic() + 0.2
            while time.monotonic() < deadline:
                drain()
            for value in b"abcd":
                process.stdin.write(bytes([value])); process.stdin.flush()
                deadline = time.monotonic() + 0.15
                while time.monotonic() < deadline:
                    drain()
            expect(rb"BUFSTORM lines=4 bytes=4\n", start)
            expect(rb"sh> ", start)
            assert bytes(output[start:]) == b"bufstorm\naabbccddBUFSTORM lines=4 bytes=4\nsh> "
            print("PASS: gift hi/badecall; missing exec returns to Shell; fork isolation, signed status, invalid wait/exec, reuse and full capacity")
            print("PASS: gift bufstorm makes four stream reads, consumes/echoes exactly four paced bytes and returns to Shell")

            start = len(output)
            trap_start = traps.stat().st_size
            process.stdin.write(b"spin\n"); process.stdin.flush()
            expect(rb"spin 0\n", start)
            deadline = time.monotonic() + 0.25
            while time.monotonic() < deadline:
                drain()
            command("stop")
            records = memory(symbols["processes"], 40)
            assert records[2] == 4
            running = [records[i:i+10] for i in range(0, 40, 10) if records[i+2] == 1]
            assert len(running) == 1 and running[0][4] == 1
            assert b"sh> " not in bytes(output[start:])
            cpu = command("info registers")
            match = re.search(r"\bsatp\s+([0-9a-fA-F]+)", cpu)
            assert match, cpu
            user_satp = 0x8000000000000000 | (running[0][1] >> 12)
            kernel_satp = 0x8000000000000000 | (symbols["root"] >> 12)
            observed_satp = int(match[1], 16)
            assert observed_satp in (user_satp, kernel_satp), cpu
            # spin repeatedly calls printf. A stop can catch its write syscall.
            if observed_satp == kernel_satp:
                spin_frame = memory(running[0][8], 36)
                assert spin_frame[1] == running[0][7] and spin_frame[3] < running[0][9]
                sp = re.search(r"\bx2/sp\s+([0-9a-fA-F]+)", cpu)
                # uservec initially loads the exact stack top before C pushes.
                assert sp and running[0][7] - 8192 <= int(sp[1], 16) <= running[0][7], cpu
            assert "user_ecall" in traps.read_text()[trap_start:]
            command("cont")
            process.stdin.write(b"Z"); process.stdin.flush()
            expect(rb"Z", start)
            deadline = time.monotonic() + 0.15
            while time.monotonic() < deadline:
                drain()
            command("stop")
            assert b"sh> " not in bytes(output[start:])
            events = [line for line in traps.read_text().splitlines() if line.strip()]
            assert all("user_ecall" in line or "s_external" in line for line in events), events[-10:]
            assert "PROCTEST FAIL" not in output.decode(errors="replace") and "fork failed" not in output.decode(errors="replace")
            target = pathlib.Path("labs/lab2/evidence")
            target.mkdir(exist_ok=True)
            (target / "phase4-shell.txt").write_bytes(output)
            print("PASS: spin prints through real user ecalls; its page table/frame/private kernel stack are selected; Shell waits; UART echoes Z")
            print("PASS: no unexpected traps; spin is intentionally endless without timer preemption")
            print(f"PASS: Lab1 startup prefix unchanged ({len(banner)} bytes); transcript saved to labs/lab2/evidence/phase4-shell.txt")
        finally:
            connection.close()
            selector.close()
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait()
            for stream in (process.stdin, process.stdout, process.stderr):
                stream.close()


if __name__ == "__main__":
    main()
