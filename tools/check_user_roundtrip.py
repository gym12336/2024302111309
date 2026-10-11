#!/usr/bin/env python3
"""Check real user calls, getpid/write/exit, memory boundaries and 31 registers."""
import pathlib
import re
import socket
import subprocess
import tempfile
import time


def main(kernel_path="kernel/kernel", exit_status=7):
    symbols = {}
    for line in subprocess.check_output(["riscv64-unknown-elf-nm", str(kernel_path)], text=True).splitlines():
        parts = line.split()
        if len(parts) == 3:
            symbols[parts[2]] = int(parts[0], 16)
    with tempfile.TemporaryDirectory(prefix="lab2-roundtrip-") as folder:
        folder = pathlib.Path(folder)
        monitor, serial, traps = [folder / name for name in ("monitor.sock", "serial", "traps")]
        process = subprocess.Popen([
            "qemu-system-riscv64", "-machine", "virt", "-bios", "none",
            "-kernel", str(kernel_path), "-display", "none", "-serial", "file:" + str(serial),
            "-monitor", "unix:" + str(monitor) + ",server,nowait", "-d", "int", "-D", str(traps),
        ], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 10
            while not monitor.exists():
                if process.poll() is not None:
                    raise RuntimeError(process.stderr.read().decode())
                if time.monotonic() > deadline:
                    raise RuntimeError("QEMU monitor did not start")
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

                def memory(address, count):
                    output = command(f"xp /{count}gx 0x{address:x}")
                    values = []
                    for line in output.splitlines():
                        match = re.match(r"^[0-9a-fA-F]+:\s+(.*)", line)
                        if match:
                            values.extend(int(v, 16) for v in re.findall(r"0x[0-9a-fA-F]+", match[1]))
                    if len(values) != count:
                        raise RuntimeError(f"could not read {count} physical words")
                    return values

                while True:
                    command("stop")
                    flag = memory(symbols["probe_stack"] + 0xff8, 1)[0]
                    if flag == 0x4641494c:
                        raise RuntimeError("user executed instructions after exit")
                    if flag == 0x50415353 and memory(symbols["boot_process"] + 16, 1) == [2]:
                        registers = command("info registers")
                        pc = re.search(r"\bpc\s+([0-9a-fA-F]+)", registers)
                        if pc and symbols["proc_exit_idle"] <= int(pc[1], 16) < symbols["proc_exit_idle_end"]:
                            break
                    if time.monotonic() > deadline:
                        raise RuntimeError("kernel exit wait not reached; trap log: " + traps.read_text()[:1800])
                    command("cont")
                    time.sleep(0.05)
                registers = command("info registers")
                snapshot = memory(symbols["probe_stack"] + 0xf00, 31)
                results = memory(symbols["probe_stack"] + 0xe00, 12)
                frame = memory(symbols["boot_trapframe"], 36)
                low = memory(symbols["user_low_l0"], 4)
                high = memory(symbols["user_high_l0"] + 510 * 8, 2)
                roots = memory(symbols["user_root"], 3)
                process_record = memory(symbols["boot_process"], 4)
            expected = [0x100 + reg for reg in range(1, 32)]
            expected[1], expected[9], expected[16] = 0x4000, 0xffffffffffffffff, 999
            final_expected = expected.copy()
            final_expected[4], final_expected[5] = 0x3ff8, 0x50415353
            final_expected[9], final_expected[16] = exit_status & ((1 << 64) - 1), 2
            if snapshot != expected or frame[5:] != final_expected:
                raise RuntimeError(f"register mismatch: snapshot={snapshot!r}; frame={frame[5:]!r}")
            error = 0xffffffffffffffff
            if results != [1, error, error, error, 3, 3, error, error, error, error, 0, 1]:
                raise RuntimeError(f"getpid/write results are incorrect: {results!r}")
            exit_epc = 0x1000 + symbols["user_probe_exit"] - symbols["user_probe_start"]
            final_epc = exit_epc + 4
            kernel_satp = 0x8000000000000000 | (symbols["root"] >> 12)
            if frame[:5] != [kernel_satp, symbols["trap_stack"] + 8192, symbols["usertrap"], final_epc, 0]:
                raise RuntimeError("kernel environment or return epc is incorrect")
            for name, expected_value in [
                ("satp", kernel_satp), ("sepc", exit_epc),
                ("stvec", symbols["kernel_trap_entry"]), ("x4/tp", 0),
            ]:
                match = re.search(r"\b" + re.escape(name) + r"\s+([0-9a-fA-F]+)", registers)
                if not match or int(match[1], 16) != expected_value:
                    raise RuntimeError(f"CPU {name} mismatch: {registers}")
            sp = re.search(r"\bx2/sp\s+([0-9a-fA-F]+)", registers)
            if not sp or not symbols["trap_stack"] <= int(sp[1], 16) < symbols["trap_stack"] + 8192:
                raise RuntimeError("exit did not keep the kernel trap stack")
            if process_record != [1, symbols["user_root"], 2, exit_status & ((1 << 64) - 1)]:
                raise RuntimeError(f"PID/state/exit status mismatch: {process_record!r}")
            def pte(address, flags):
                return ((address >> 12) << 10) | flags
            if low != [0, pte(symbols["probe_code"], 0x5b), 0, pte(symbols["probe_stack"], 0xd7)]:
                raise RuntimeError("code/stack permissions or guard pages are incorrect")
            if high != [pte(symbols["boot_trapframe"], 0xc7), pte(symbols["trampoline"], 0x4b)] or roots[1:] != [0, 0]:
                raise RuntimeError("supervisor trampoline/frame or kernel isolation is incorrect")
            events = [line for line in traps.read_text().splitlines() if line.strip()]
            expected_traps = [0x1000 + symbols[label] - symbols["user_probe_start"] for label in
                              ("user_probe_start", "user_probe_getpid_first", "user_probe_wide",
                               "user_probe_zero", "user_probe_badfd", "user_probe_write_stack",
                               "user_probe_write_code", "user_probe_badptr", "user_probe_supervisor",
                               "user_probe_cross", "user_probe_negative", "user_probe_empty", "user_probe_getpid_last",
                               "user_probe_exit")]
            observed_traps = []
            for event in events:
                match = re.search(r"epc:0x([0-9a-fA-F]+)", event)
                if "user_ecall" not in event or not match:
                    raise RuntimeError("unexpected hardware exception: " + event)
                observed_traps.append(int(match[1], 16))
            if observed_traps != expected_traps:
                raise RuntimeError(f"hardware trap sequence mismatch: {observed_traps!r}")
            if serial.read_bytes() != pathlib.Path("expect_banner.txt").read_bytes() + b"Hi\nOK\n":
                raise RuntimeError("Lab1 prefix or raw user output changed; an invalid write may have leaked bytes")
            print("PASS: 14 hardware U-mode ecalls in the expected order; no unexpected exceptions")
            print("PASS: stdout stack buffer and stderr code buffer each write 3 bytes: Hi\\nOK\\n")
            print("PASS: bad fd/null/supervisor/cross-page/negative count return -1 with no extra output")
            print("PASS: zero-length write returns 0; getpid still returns 1; invalid call numbers return -1")
            print("PASS: all 31 original register snapshots match; final frame contains the exit request")
            print(f"PASS: exit({exit_status}) records PID=1, state=EXITED and signed status={exit_status}")
            print("PASS: exit never returns to user; PASS marker preserved; CPU waits on kernel satp/stack/tp/stvec")
            print(f"PASS: hardware sepc=0x{exit_epc:x}; frame epc=0x{final_epc:x} is not used to return")
            print("PASS: user code RX, stack RW; guard pages unmapped; trampoline/frame have no PTE_U")
            print("PASS: Lab1 prefix matches all 446 bytes; user output matches all 6 raw bytes")
            print("TRACE: user ecall addresses=" + ", ".join(f"0x{address:x}" for address in observed_traps))
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
