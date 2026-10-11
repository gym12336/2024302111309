#!/usr/bin/env python3
"""Run in WSL: compare C field offsets with the course trampoline assembly."""
from pathlib import Path
import re
import subprocess
import tempfile


def main():
    root = Path(__file__).resolve().parent.parent
    asm = (root / "kernel/trampoline.S").read_text(encoding="utf-8")
    save, restore = asm.split("uservec:", 1)[1].split("userret:", 1)
    loads = re.findall(r"^\s*ld\s+(\w+),\s*(\d+)\(a0\)", restore, re.MULTILINE)
    stores = re.findall(r"^\s*sd\s+(\w+),\s*(\d+)\(a0\)", save, re.MULTILINE)
    registers = {"ra", "sp", "gp", "tp"}
    registers.update(f"t{i}" for i in range(7))
    registers.update(f"s{i}" for i in range(12))
    registers.update(f"a{i}" for i in range(8))
    if len(loads) != 31 or {reg for reg, _ in loads} != registers:
        raise SystemExit("FAIL: userret must restore all 31 writable registers")
    if len(stores) != 31:
        raise SystemExit("FAIL: uservec must save 31 writable registers")
    checks = ['#include "trapframe.h"']
    for reg, offset in loads:
        # uservec saves a0 through sscratch and t0 after a0 becomes the base.
        source = "t0" if reg == "a0" else reg
        if (source, offset) not in stores:
            raise SystemExit(f"FAIL: missing save for {reg} at offset {offset}")
        checks.append(
            f'_Static_assert(__builtin_offsetof(struct trapframe, {reg}) == '
            f'{offset}, "assembly offset mismatch: {reg}");'
        )
    with tempfile.TemporaryDirectory(prefix="lab2-trapframe-") as tmp:
        probe = Path(tmp) / "layout.c"
        probe.write_text("\n".join(checks) + "\n", encoding="utf-8")
        compiler = ["riscv64-unknown-elf-gcc", "-Wall", "-Werror", "-std=gnu99",
                    "-march=rv64gc", "-ffreestanding", "-fsyntax-only",
                    "-I", str(root / "kernel"), str(probe)]
        subprocess.run(compiler, check=True)

        # Swap two fields only in a temporary copy: its own guards must reject it.
        header = (root / "kernel/trapframe.h").read_text(encoding="utf-8")
        header = header.replace("uint64 a0;", "uint64 swap_a0;")
        header = header.replace("uint64 a1;", "uint64 a0;")
        header = header.replace("uint64 swap_a0;", "uint64 a1;")
        (Path(tmp) / "trapframe.h").write_text(header, encoding="utf-8")
        probe.write_text('#include "trapframe.h"\n', encoding="utf-8")
        bad = subprocess.run(compiler, capture_output=True, text=True)
        if bad.returncode == 0 or "trapframe offset mismatch" not in bad.stderr:
            raise SystemExit("FAIL: field-swap negative check did not reject the layout")
    print("PASS: 31 register save/restore offsets match the compiled C layout")
    print("PASS: 36 fields, 288 bytes; a0=112, a7=168, sp=48, epc=24")
    print("PASS: swapping a0/a1 in a temporary header is rejected by the compiler")


if __name__ == "__main__":
    main()
