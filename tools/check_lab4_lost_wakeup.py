#!/usr/bin/env python3
"""Reproduce a lost wakeup in an isolated, intentionally broken kernel.

The formal source and kernel/kernel are never replaced. A deliberate yield
forces the producer into the unlocked window: this baseline does not preempt
kernel C code, so a delay alone cannot force a child to run on the same hart.
"""
import os
import pathlib
import selectors
import subprocess
import tempfile
import time


def main():
    root = pathlib.Path(__file__).resolve().parents[1]
    os.chdir(root)
    evidence = root / 'labs/lab4/evidence'
    evidence.mkdir(parents=True, exist_ok=True)
    source = pathlib.Path('kernel/proc.c').read_text()
    correct = '  acquire(&p->lock);\n  release(lk);\n  p->chan = chan;'
    broken = ('  release(lk);\n'
              '  for (volatile int i = 0; i < 1000000; i++) ;\n'
              '  if (lk == &wait_lock) {\n'
              '    printf("FAULT: wait condition unlocked before SLEEPING\\n");\n'
              '    yield(); // force the child exit into the lost-wakeup window\n'
              '  }\n'
              '  acquire(&p->lock);\n  p->chan = chan;')
    assert source.count(correct) == 1
    output = bytearray()
    with tempfile.TemporaryDirectory(prefix='lab4-lost-wakeup-') as folder:
        folder = pathlib.Path(folder)
        mutant = folder / 'proc.c'
        mutant.write_text(source.replace(correct, broken))
        obj = folder / 'proc.o'
        flags = ['-Wall', '-Werror', '-O', '-std=gnu99', '-mcmodel=medany',
                 '-ffreestanding', '-nostdlib', '-fno-common', '-march=rv64gc',
                 '-fno-stack-protector', '-fno-pie', '-Ikernel']
        subprocess.run(['riscv64-unknown-elf-gcc', *flags, '-c', str(mutant),
                        '-o', str(obj)], check=True)
        objects = subprocess.check_output(
            ['make', '-s', '--no-print-directory', '--eval',
             'lab4-print-objects:;@echo $(OBJS)', 'lab4-print-objects'], text=True).strip().split()
        kernel = folder / 'broken.elf'
        subprocess.run(['riscv64-unknown-elf-ld', '-T', 'kernel/kernel.ld', '-o', str(kernel),
                        *[str(obj) if name == 'kernel/proc.o' else name for name in objects]], check=True)
        process = subprocess.Popen(['qemu-system-riscv64', '-machine', 'virt',
                                    '-bios', 'none', '-kernel', str(kernel), '-smp', '1',
                                    '-nographic'], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, bufsize=0)
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)

        def read_until(pattern, seconds):
            end = time.monotonic() + seconds
            while pattern not in output and time.monotonic() < end:
                for key, _ in selector.select(.1):
                    data = os.read(key.fd, 65536)
                    if not data:
                        raise AssertionError('fault kernel exited')
                    output.extend(data)
            return pattern in output

        try:
            assert read_until(b'sh> ', 10), output
            process.stdin.write(b'bench\n')
            process.stdin.flush()
            assert read_until(b'F.A.U.L.T.:.', 10), output
            # The child exit's wakeup ran while its parent was RUNNABLE.
            # The parent then sleeps, with no remaining child exit to wake it.
            completed = read_until(b'PASS: bench', 3)
            assert not completed and b'RESULT avg_fork_wait' not in output, output
            note = ('EXPECTED FAILURE REPRODUCED: bench blocked in first fork/wait round.\n'
                    'Mutation: release(condition lock), delay, forced yield, acquire(p->lock).\n'
                    'The forced yield controls the interleaving on a kernel that only preempts user mode.\n'
                    'Formal proc.c and kernel/kernel were never modified.\n')
            (evidence / 'lost-wakeup.txt').write_bytes(output + b'\n' + note.encode())
            print(note, end='')
        finally:
            process.kill()
            process.wait()
            selector.close()


if __name__ == '__main__':
    main()
