#!/usr/bin/env python3
"""Check immutable Lab2 originals and the explicit official Lab3 v2 overlay."""
import pathlib
import zipfile


def main():
    root = pathlib.Path(__file__).resolve().parents[1]
    count = 0
    lab3 = root / "labs/lab3"
    overrides = {
        "kernel/trampoline.S": "gifts/kernel/trampoline.S",
        "kernel/riscv.h": "gifts/kernel/riscv.h",
    }
    lab3_files = {
        **{source: target for target, source in overrides.items()},
        "gifts/dump_pagetable-ABI.md": "gifts/dump_pagetable-ABI.md",
        "gifts/dump-callpoint-ABI.md": "gifts/dump-callpoint-ABI.md",
        "support/tests/badaccess.c": "support/tests/badaccess.c",
        "support/tests/memcap.c": "support/tests/memcap.c",
        # Keep the Lab2 README intact; install this version under a distinct name.
        "support/tests/README-tests.md": "support/tests/README-lab3-tests.md",
    }
    with zipfile.ZipFile(lab3 / "lab3-v2-20260929.zip") as update, \
         zipfile.ZipFile(root / "labs/lab2/lab2.zip") as archive:
        for name in archive.namelist():
            if name.endswith("/"):
                continue
            if name.startswith("gifts/"):
                expected = archive.read(name)
                assert (root / name).read_bytes() == expected, name
                relative = name[len("gifts/"):]
                installed = "support/" + relative if relative.startswith("tests/") else relative
                installed_expected = update.read(overrides[installed]) if installed in overrides else expected
                assert (root / installed).read_bytes() == installed_expected, installed
                count += 1
        name = "support/inject_uart.py"
        assert (root / name).read_bytes() == archive.read(name), name
        for source, installed in lab3_files.items():
            expected = update.read(source)
            assert (lab3 / source).read_bytes() == expected, "lab3 original: " + source
            assert (root / installed).read_bytes() == expected, "lab3 installed: " + installed
    print(f"PASS: all {count} Lab2 gifted originals are unchanged; installed copies match except the two explicit Lab3 v2 overrides")
    print(f"PASS: all {len(lab3_files)} Lab3 v2 support files and installed copies match their ZIP byte for byte")
    print("PASS: original support/inject_uart.py is unchanged; compatibility adaptation exists only in our wrapper")


if __name__ == "__main__":
    main()
