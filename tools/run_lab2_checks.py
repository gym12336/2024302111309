#!/usr/bin/env python3
"""Reproduce Lab2 acceptance and save actual outputs. Run inside WSL."""
import argparse
import os
import pathlib
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--clean", action="store_true", help="rebuild kernel and generated users from source")
    args = parser.parse_args()
    root = pathlib.Path(__file__).resolve().parents[1]
    os.chdir(root)
    evidence = root / "labs/lab2/evidence"
    evidence.mkdir(exist_ok=True)
    if args.clean:
        # Check every directory/file targeted by the immutable clean-extra rule.
        for name in ("kernel", "user-flat", "kernel/userimg.S", "user/usys.S"):
            target = (root / name).resolve()
            if not target.is_relative_to(root) or target == root:
                raise RuntimeError(f"clean target escapes workspace: {target}")
        subprocess.run(["make", "clean"], check=True)
        subprocess.run(["make", "clean-extra"], check=True)
    checks = [["make"], [sys.executable, "tools/check_expect.py", "2024302111309"]]
    checks += [[sys.executable, "tools/" + name + ".py"] for name in
               ("check_course_files", "check_trapframe", "check_trap_prepare", "check_exit",
                "check_kernel_irq", "check_uart_irq", "check_console_ring", "check_user_copyout",
                "check_read", "check_read_pressure", "check_shell")]
    for stem in ("lab2-stream", "lab2-long-storm"):
        checks.append([sys.executable, "tools/run_course_inject.py", "--tree", ".",
                       "--script", f"support/{stem}.txt", "--log",
                       f"labs/lab2/evidence/{stem}-inject.txt"])
    with (evidence / "phase4-checks.txt").open("w", encoding="utf-8") as log:
        for command in checks:
            label = "$ " + " ".join(command)
            print(label, flush=True)
            result = subprocess.run(command, text=True, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, timeout=90)
            log.write(label + "\n" + result.stdout + f"exit={result.returncode}\n\n")
            log.flush()
            print(result.stdout, end="", flush=True)
            if result.returncode:
                raise SystemExit(result.returncode)
        message = f"PASS: build and all {len(checks)-1} acceptance checks passed; formal kernel still boots Shell"
        print(message, flush=True)
        log.write(message + "\n")


if __name__ == "__main__":
    main()
