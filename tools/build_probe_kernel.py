"""Build the earlier probe in isolation while the formal kernel boots Shell."""
import pathlib
import subprocess


def build(folder, status=7):
    folder = pathlib.Path(folder)
    flags = ["-Wall", "-Werror", "-O", "-std=gnu99", "-mcmodel=medany",
             "-ffreestanding", "-nostdlib", "-fno-common", "-march=rv64gc",
             "-fno-stack-protector", "-fno-pie", "-Ikernel"]
    main = folder / "main.o"
    probe = folder / "probe.o"
    subprocess.run(["riscv64-unknown-elf-gcc", *flags, "-DLAB2_BOOT_PROBE",
                    "-c", "kernel/main.c", "-o", str(main)], check=True)
    subprocess.run(["riscv64-unknown-elf-gcc", *flags, f"-DPROBE_EXIT_STATUS={status}",
                    "-c", "kernel/user_probe.S", "-o", str(probe)], check=True)
    objects = ["entry", "start", "console", "printf", "userimg", "trampoline_link",
               "boot_vm", "trap", "kernel_trap_entry", "user_boot", "proc", "syscall",
               "user_mem", "plic", "kalloc", "vm", "vm_printf"]
    kernel = folder / "probe.elf"
    subprocess.run(["riscv64-unknown-elf-ld", "-T", "kernel/kernel.ld", "-o", str(kernel),
                    *[f"kernel/{name}.o" for name in objects], str(main), str(probe)], check=True)
    return kernel
