#!/usr/bin/env python3
"""Build and accept Lab4's single-hart ID9 scheduler through real QEMU UART."""
import argparse
import os
import pathlib
import re
import selectors
import subprocess
import sys
import time


def serial_checks(evidence, report):
    process = subprocess.Popen(
        ['qemu-system-riscv64', '-machine', 'virt', '-bios', 'none',
         '-kernel', 'kernel/kernel', '-smp', '1', '-nographic'],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, bufsize=0)
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    output = bytearray()

    def expect(pattern, start=0, timeout=120):
        deadline = time.monotonic() + timeout
        while not re.search(pattern, output[start:]):
            segment = output[start:]
            if b'FAIL:' in segment:
                raise AssertionError(f'guest test failed: {segment!r}')
            if b'panic:' in segment.lower() or b'p.a.n.i.c.' in segment.lower():
                raise AssertionError(f'kernel panic: {segment!r}')
            if pattern != rb'sh> ' and b'sh> ' in segment:
                raise AssertionError(f'returned to shell without {pattern!r}: {segment!r}')
            if time.monotonic() > deadline:
                raise AssertionError(f'missing {pattern!r}: {output[start:]!r}')
            for key, _ in selector.select(.1):
                chunk = os.read(key.fd, 65536)
                if not chunk:
                    raise AssertionError('QEMU exited before acceptance finished')
                output.extend(chunk)

    def passed(label):
        line = 'PASS: ' + label
        print(line, flush=True)
        report.write(line + '\n')
        report.flush()

    try:
        expect(rb'sh> ')
        assert output.startswith(pathlib.Path('expect_banner.txt').read_bytes()), 'Lab1 banner'
        passed('single-hart boot and Lab1 banner')
        for command, patterns in [
            ('hi', [rb'hi: user program running']),
            ('badaccess', [rb'TEST-3a PASS', rb'TEST-3b PASS']),
            ('pagedump', [rb'DUMP-PAGETABLE begin', rb'DUMP-PAGETABLE end']),
            ('bench', [rb'RESULT avg_fork_wait = [0-9]+',
                       rb'RESULT concurrent_children = 8', rb'PASS: bench']),
            ('alt', [rb'alt done', rb'PASS: alt']),
            ('schedcheck', [rb'PASS: schedcheck']),
            ('priority_test', [rb'RESULT priority_cpu = [0-9]+:[0-9]+',
                               rb'RESULT aging_two_cpu_ticks_elapsed = [0-9]+ ticks',
                               rb'RESULT equal_priority_cpu = [0-9]+:[0-9]+',
                               rb'PASS: priority ID9']),
        ]:
            start = len(output)
            process.stdin.write((command + '\n').encode())
            process.stdin.flush()
            for pattern in patterns:
                expect(pattern, start)
            expect(rb'sh> ', start)
            chunk = output[start:]
            assert b'FAIL:' not in chunk and b'panic' not in chunk.lower(), chunk
            if command == 'alt':
                letters = re.search(rb'\n([AB]+)\nalt done', chunk)
                assert letters is not None, chunk
                runs = re.findall(rb'A+|B+', letters.group(1))
                assert len(runs) > 2, 'alt did not interleave compute-bound children'
                assert letters.group(1).count(b'A') == 16 and letters.group(1).count(b'B') == 16
            if command == 'pagedump':
                assert b'perm=r-xu' in chunk and b'perm=rw-u' in chunk, chunk
            passed(command + ' and return to shell')
        passed('all Lab4 serial checks')
    finally:
        process.kill()
        process.wait()
        selector.close()
        (evidence / 'runtime-serial.txt').write_bytes(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skip-build', action='store_true')
    args = parser.parse_args()
    root = pathlib.Path(__file__).resolve().parents[1]
    os.chdir(root)
    evidence = root / 'labs/lab4/evidence'
    evidence.mkdir(parents=True, exist_ok=True)
    with (evidence / 'checks.txt').open('w', encoding='utf-8') as report:
        if not args.skip_build:
            report.write('$ make\n')
            result = subprocess.run(['make'], stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True, timeout=120)
            report.write(result.stdout + f'\nexit={result.returncode}\n')
            if result.returncode:
                print(result.stdout, end='')
                raise SystemExit(result.returncode)
        try:
            serial_checks(evidence, report)
            command = [sys.executable, 'tools/run_course_inject.py', '--tree', '.',
                       '--script', 'labs/lab4/uart-regression.txt',
                       '--log', 'labs/lab4/evidence/uart-regression.txt']
            report.write('$ ' + ' '.join(command) + '\n')
            result = subprocess.run(command, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True, timeout=120)
            report.write(result.stdout + f'\nexit={result.returncode}\n')
            print(result.stdout, end='', flush=True)
            if result.returncode:
                raise AssertionError('Lab2 course UART regression failed')
            report.write('PASS: all Lab4 acceptance checks\n')
            print('PASS: all Lab4 acceptance checks', flush=True)
        except Exception as error:
            report.write('FAIL: ' + str(error) + '\n')
            raise


if __name__ == '__main__':
    main()
