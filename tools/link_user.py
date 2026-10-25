import subprocess, sys
args = ["user-flat/user-lab3.ld" if a == "user/user.ld" else a for a in sys.argv[1:]]
raise SystemExit(subprocess.call(["riscv64-unknown-elf-ld", *args]))
