#!/usr/bin/env python3
"""Check default exit(7), plus isolated test kernels for exit(0) and exit(-3)."""
import pathlib
import subprocess
import tempfile

from check_user_roundtrip import main as check_kernel


def main():
    check_kernel()
    objects = ["entry", "start", "console", "printf", "main", "userimg",
               "trampoline_link", "boot_vm", "trap", "kernel_trap_entry",
               "user_boot", "proc", "syscall", "user_mem", "plic"]
    with tempfile.TemporaryDirectory(prefix="lab2-exit-") as folder:
        folder = pathlib.Path(folder)
        for status in (0, -3):
            probe = folder / f"probe{status}.o"
            kernel = folder / f"exit{status}.elf"
            subprocess.run([
                "riscv64-unknown-elf-gcc", "-Wall", "-Werror", "-O", "-mcmodel=medany",
                "-ffreestanding", "-nostdlib", "-fno-common", "-march=rv64gc",
                "-fno-stack-protector", "-fno-pie", "-Ikernel",
                f"-DPROBE_EXIT_STATUS={status}", "-c", "kernel/user_probe.S", "-o", str(probe),
            ], check=True)
            subprocess.run([
                "riscv64-unknown-elf-ld", "-T", "kernel/kernel.ld", "-o", str(kernel),
            ] + [f"kernel/{name}.o" for name in objects] + [str(probe)], check=True)
            check_kernel(kernel, status)
    print("PASS: exit statuses 7, 0 and -3 all terminate; formal kernel was not replaced")


if __name__ == "__main__":
    main()
