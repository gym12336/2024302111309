#!/usr/bin/env python3
"""Real serial acceptance, including OOM, recovery, guard, copy and isolation."""
import os
import pathlib
import re
import selectors
import subprocess
import time


def main():
    root = pathlib.Path(__file__).resolve().parents[1]
    os.chdir(root)
    evidence = root / 'labs/lab3/evidence'
    evidence.mkdir(exist_ok=True)
    process = subprocess.Popen(['qemu-system-riscv64', '-machine', 'virt',
                               '-bios', 'none', '-kernel', 'kernel/kernel',
                               '-nographic'], stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=0)
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    output = bytearray()
    def expect(pattern, start=0, timeout=90):
        deadline = time.monotonic()+timeout
        while not re.search(pattern, output[start:]):
            if time.monotonic() > deadline:
                raise AssertionError(f'missing {pattern!r}: {output[start:]!r}')
            for key, _ in selector.select(.1):
                chunk = os.read(key.fd, 65536)
                if not chunk:
                    raise AssertionError('QEMU exited')
                output.extend(chunk)
    try:
        expect(rb'sh> ')
        banner = pathlib.Path('expect_banner.txt').read_bytes()
        assert output.startswith(banner), 'Lab1 banner changed'
        text = output.decode()
        assert 'DUMP-PAGETABLE begin\n' in text
        assert 'va=0x0 ' in text and 'perm=r-xu' in text
        assert 'LEAF va=0x2000 ' not in text and 'LEAF va=0x3000 ' not in text
        assert 'perm=rw--' in text and 'perm=r-x-' in text
        for command, patterns in [
            ('badaccess', [rb'TEST-3a PASS', rb'TEST-3b PASS']),
            ('vmtest', [rb'CROSS-PAGE PASS', rb'GUARD PASS', rb'SHRINK PASS', rb'EXEC-FAIL PASS',
                        rb'OOM-FORK-EXEC PASS', rb'UNALIGNED-SBRK PASS']),
            ('proctest', [rb'PROCTEST PASS']),
            ('memcap', [rb'TEST-4 PASS']),
            ('memcap', [rb'TEST-4 PASS']),
            ('hi', [rb'hi: user program running']),
            ('pagedump', [rb'DUMP-PAGETABLE begin', rb'DUMP-PAGETABLE end']),
        ]:
            start = len(output)
            process.stdin.write((command+'\n').encode())
            process.stdin.flush()
            for pattern in patterns:
                expect(pattern, start)
            expect(rb'sh> ', start)
            assert b' FAIL' not in output[start:], output[start:]
            print(f'PASS: {command}', flush=True)
        start = len(output)
        process.stdin.write(b'vmconcurrent\n')
        process.stdin.flush()
        expect(rb'CONCURRENT shell and spin', start)
        expect(rb'spin [0-9]+', start)
        expect(rb'sh> ', start)
        start = len(output)
        process.stdin.write(b'hi\n')
        process.stdin.flush()
        expect(rb'hi: user program running', start)
        expect(rb'spin [0-9]+', start)
        expect(rb'sh> ', start)
        print('PASS: spin and sh run concurrently; sh executes hi')
        print('PASS: Lab1 banner, page dump, guards, copies, fork/exec, repeated OOM and shell recovery')
    finally:
        process.kill()
        process.wait()
        (evidence/'runtime-serial.txt').write_bytes(output)
        selector.close()


if __name__ == '__main__':
    main()
