#!/usr/bin/env python3
"""Verify the Lab3 support merge and its C/assembly build contracts in WSL."""
import os
import pathlib
import re
import subprocess
import sys


def main():
    root = pathlib.Path(__file__).resolve().parents[1]
    os.chdir(root)
    subprocess.run([sys.executable, "tools/check_course_files.py"], check=True)
    subprocess.run(["make"], check=True)

    # Repeating this header used to redefine its static inline functions.
    source = ('#include "kernel/types.h"\n'
              '#include "kernel/riscv.h"\n'
              '#include "kernel/riscv.h"\n'
              'int header_probe(void) { return PGSIZE; }\n')
    subprocess.run(["riscv64-unknown-elf-gcc", "-Wall", "-Werror", "-I.",
                    "-march=rv64gc", "-fsyntax-only", "-x", "c", "-"],
                   input=source, text=True, check=True)
    print("PASS: riscv.h may be included twice without redefinitions", flush=True)

    # Check actual linked symbols, rather than assuming a source directive worked.
    symbols = {}
    for line in subprocess.check_output(
            ["riscv64-unknown-elf-nm", "kernel/kernel"], text=True).splitlines():
        fields = line.split()
        if len(fields) == 3:
            symbols[fields[2]] = int(fields[0], 16)
    base = symbols["trampoline"]
    assert base >= 0x80000000 and base % 4096 == 0, hex(base)
    for name in ("uservec", "userret"):
        assert base <= symbols[name] < base + 4096, (name, hex(symbols[name]))
    sections = subprocess.check_output(
        ["riscv64-unknown-elf-readelf", "-SW", "kernel/kernel"], text=True)
    section = next(line for line in sections.splitlines() if ".trampsec " in line)
    assert re.search(r"\bAX\b", section), section
    print(f"PASS: trampoline={base:#x}, uservec={symbols['uservec']:#x}, "
          f"userret={symbols['userret']:#x}; one aligned allocated/executable page",
          flush=True)

    # -W pretends the included source changed; -n proves dependency without edits.
    recipe = subprocess.check_output(
        ["make", "-n", "-W", "kernel/trampoline.S", "kernel/trampoline_link.o"],
        text=True)
    assert "-c -o kernel/trampoline_link.o kernel/trampoline_link.S" in recipe, recipe
    print("PASS: changing trampoline.S schedules its wrapper object for rebuild",
          flush=True)


if __name__ == "__main__":
    main()
