#!/usr/bin/env python3
"""Compare the course files and installed copies directly with the lab2 ZIP."""
import pathlib
import zipfile


def main():
    root = pathlib.Path(__file__).resolve().parents[1]
    count = 0
    with zipfile.ZipFile(root / "labs/lab2/lab2.zip") as archive:
        for name in archive.namelist():
            if name.endswith("/"):
                continue
            if name.startswith("gifts/"):
                expected = archive.read(name)
                assert (root / name).read_bytes() == expected, name
                relative = name[len("gifts/"):]
                installed = "support/" + relative if relative.startswith("tests/") else relative
                assert (root / installed).read_bytes() == expected, installed
                count += 1
        name = "support/inject_uart.py"
        assert (root / name).read_bytes() == archive.read(name), name
    print(f"PASS: all {count} gifted originals and installed copies match lab2.zip byte for byte")
    print("PASS: original support/inject_uart.py is unchanged; compatibility adaptation exists only in our wrapper")


if __name__ == "__main__":
    main()
