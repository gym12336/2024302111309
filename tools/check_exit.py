#!/usr/bin/env python3
"""Check isolated test kernels for exit(7), exit(0) and exit(-3)."""
import tempfile

from check_user_roundtrip import main as check_kernel
from build_probe_kernel import build


def main():
    with tempfile.TemporaryDirectory(prefix="lab2-exit-") as folder:
        for status in (7, 0, -3):
            check_kernel(build(folder, status), status)
    print("PASS: exit statuses 7, 0 and -3 all terminate; formal kernel was not replaced")


if __name__ == "__main__":
    main()
