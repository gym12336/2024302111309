#!/usr/bin/env python3
"""Check the boot trapframe in running QEMU; run from the repo in WSL."""
import pathlib
import re
import socket
import subprocess
import tempfile
import time


def main():
    symbols = {}
    for line in subprocess.check_output(
        ["riscv64-unknown-elf-nm", "kernel/kernel"], text=True
    ).splitlines():
        parts = line.split()
        if len(parts) == 3:
            symbols[parts[2]] = int(parts[0], 16)
    expected_banner = pathlib.Path("expect_banner.txt").read_bytes()
    with tempfile.TemporaryDirectory(prefix="lab2-env-") as directory:
        directory = pathlib.Path(directory)
        monitor = directory / "monitor.sock"
        serial = directory / "serial.txt"
        traps = directory / "traps.txt"
        process = subprocess.Popen([
            "qemu-system-riscv64", "-machine", "virt", "-bios", "none",
            "-kernel", "kernel/kernel", "-display", "none",
            "-serial", "file:" + str(serial),
            "-monitor", "unix:" + str(monitor) + ",server,nowait",
            "-d", "int", "-D", str(traps),
        ], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 10
            while not (monitor.exists() and serial.exists()
                       and serial.stat().st_size >= len(expected_banner)):
                if process.poll() is not None:
                    raise RuntimeError(process.stderr.read().decode())
                if time.monotonic() > deadline:
                    raise RuntimeError("QEMU did not finish the boot banner")
                time.sleep(0.05)
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(3)
                connection.connect(str(monitor))

                def receive():
                    data = b""
                    while b"(qemu) " not in data:
                        chunk = connection.recv(65536)
                        if not chunk:
                            raise RuntimeError("QEMU closed the monitor connection")
                        data += chunk
                    return data.decode(errors="replace")

                receive()

                def command(value):
                    connection.sendall(value.encode() + b"\n")
                    return receive()

                command("stop")
                memory = command("x /5gx 0x3fffffe000")
                registers = command("info registers")
            values = []
            for line in memory.splitlines():
                match = re.match(r"^[0-9a-fA-F]+:\s+(.*)", line)
                if match:
                    values.extend(int(v, 16) for v in re.findall(
                        r"0x[0-9a-fA-F]+", match.group(1)))
            expected = [0x8000000000000000 | (symbols["root"] >> 12),
                        symbols["trap_stack"] + 8192,
                        symbols["usertrap"], 0, 0]
            if values != expected:
                raise RuntimeError(f"trapframe mismatch: {values!r} != {expected!r}")
            for label, value in zip(
                ["kernel_satp", "kernel_sp", "kernel_trap", "epc", "kernel_hartid"], values
            ):
                print(f"PASS: {label}=0x{value:016x}")
            satp = re.search(r"\bsatp\s+([0-9a-fA-F]+)", registers)
            sp = re.search(r"\bx2/sp\s+([0-9a-fA-F]+)", registers)
            tp = re.search(r"\bx4/tp\s+([0-9a-fA-F]+)", registers)
            if not satp or int(satp[1], 16) != values[0]:
                raise RuntimeError("saved satp differs from the active CPU satp")
            if not sp or int(sp[1], 16) == values[1] or values[1] % 16:
                raise RuntimeError("trap stack is not separate and 16-byte aligned")
            if not tp or int(tp[1], 16) != values[4]:
                raise RuntimeError("saved hart ID differs from CPU tp")
            if serial.read_bytes() != expected_banner:
                raise RuntimeError("Lab1 banner differs from expect_banner.txt")
            if traps.read_bytes():
                raise RuntimeError("QEMU logged unexpected exceptions during boot")
            print("PASS: CPU satp/tp match; trap stack is separate and aligned to 16 bytes")
            print(f"PASS: Lab1 banner matches all {len(expected_banner)} bytes; exception log is empty")
        finally:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            process.stderr.close()


if __name__ == "__main__":
    main()
