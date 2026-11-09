#!/usr/bin/env python3
"""Check immutable course originals and explicit official Lab3/Lab4 overlays."""
import pathlib
import zipfile


def main():
    root = pathlib.Path(__file__).resolve().parents[1]
    count = 0
    lab3 = root / "labs/lab3"
    lab4 = root / "labs/lab4"
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
    # Lab4 officially replaces these Lab2 interfaces. Our sole extension is
    # syscall 26 for ID9 observation; accept exactly its documented suffix.
    lab4_interfaces = {
        "kernel/syscall.h": (
            "gifts/kernel/syscall.h", b"#define SYS_setpriority 26\n"),
        "user/user.h": (
            "gifts/user/user.h",
            b"\n// ID9: 0=low, 1=high. Return the previous base priority, or -1.\n"
            b"int setpriority(int priority);\n"),
        "user/usys.pl": (
            "gifts/user/usys.pl", b'entry("setpriority");\n'),
    }
    with zipfile.ZipFile(lab3 / "lab3-v2-20260929.zip") as update, \
         zipfile.ZipFile(root / "labs/lab2/lab2.zip") as archive, \
         zipfile.ZipFile(lab4 / "lab4-v2-20261009.zip") as scheduling:
        for name in archive.namelist():
            if name.endswith("/"):
                continue
            if name.startswith("gifts/"):
                expected = archive.read(name)
                assert (root / name).read_bytes() == expected, name
                relative = name[len("gifts/"):]
                installed = "support/" + relative if relative.startswith("tests/") else relative
                if installed in lab4_interfaces:
                    source, suffix = lab4_interfaces[installed]
                    installed_expected = scheduling.read(source) + suffix
                elif installed in overrides:
                    installed_expected = update.read(overrides[installed])
                else:
                    installed_expected = expected
                assert (root / installed).read_bytes() == installed_expected, installed
                count += 1
        name = "support/inject_uart.py"
        assert (root / name).read_bytes() == archive.read(name), name
        for source, installed in lab3_files.items():
            expected = update.read(source)
            assert (lab3 / source).read_bytes() == expected, "lab3 original: " + source
            assert (root / installed).read_bytes() == expected, "lab3 installed: " + installed
        lab4_originals = [name for name in scheduling.namelist() if not name.endswith("/")]
        for source in lab4_originals:
            assert (lab4 / source).read_bytes() == scheduling.read(source), "lab4 original: " + source
        for installed, (source, suffix) in lab4_interfaces.items():
            assert (root / installed).read_bytes() == scheduling.read(source) + suffix, "lab4 interface: " + installed
        lab4_support = {
            "gifts/kernel/swtch.S": "kernel/swtch.S",
            "support/schedstat.patch": "support/schedstat.patch",
            "support/tests/README-tests.md": "support/tests/README-lab4-tests.md",
        }
        for filename in ("common.h", "common.c", "bench.c", "lottery_test.c", "stride_test.c"):
            source = "support/tests/" + filename
            assert (root / "user" / filename).read_bytes() == scheduling.read(source), "lab4 user test: " + filename
            lab4_support[source] = source
        for source, installed in lab4_support.items():
            assert (root / installed).read_bytes() == scheduling.read(source), "lab4 installed: " + installed
    print(f"PASS: all {count} Lab2 gifted originals are unchanged; installed copies use only the explicit Lab3/Lab4 overlays")
    print(f"PASS: all {len(lab3_files)} Lab3 v2 support files and installed copies match their ZIP byte for byte")
    print(f"PASS: all {len(lab4_originals)} Lab4 v2 originals match their ZIP byte for byte")
    print("PASS: Lab4 interfaces match official bytes plus the exact allowed setpriority(26) extensions")
    print("PASS: Lab4 swtch, specification, README and all five tests in user/support match official bytes")
    print("PASS: original support/inject_uart.py is unchanged; compatibility adaptation exists only in our wrapper")


if __name__ == "__main__":
    main()
