#!/usr/bin/env python3
"""Supplement the immutable flat-image table with ELF entry and memory size."""
import pathlib
import struct
import subprocess
import sys

print("/* Generated from user ELF files; do not edit. */")
print("static const struct image_meta image_metadata[] = {")
for name in sys.argv[1:]:
    path = pathlib.Path("user-flat") / (name + ".elf")
    data = path.read_bytes()
    if data[:6] != b"\x7fELF\x02\x01":
        raise SystemExit("expected ELF64 little endian")
    entry = struct.unpack_from("<Q", data, 24)[0]
    symbols = {}
    for line in subprocess.check_output(["riscv64-unknown-elf-nm", str(path)], text=True).splitlines():
        parts = line.split()
        if len(parts) == 3:
            symbols[parts[2]] = int(parts[0], 16)
    memory = symbols["end"]
    size = path.with_suffix(".bin").stat().st_size
    if entry >= size or memory < size or memory > (1 << 38) - 8 * 4096:
        raise SystemExit(f"{name}: invalid user image bounds")
    print(f'  {{"{name}", {entry}UL, {memory}UL, {symbols["data_start"]}UL}},')
print("};")
