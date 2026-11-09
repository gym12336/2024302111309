#!/usr/bin/env python3
"""Accept real one/two-hart execution, concurrent lifecycle and VM regressions."""
import argparse
import os
import pathlib
import re
import selectors
import subprocess
import time


class Guest:
    def __init__(self, cpus):
        self.process = subprocess.Popen(
            ['qemu-system-riscv64', '-machine', 'virt', '-bios', 'none',
             '-kernel', 'kernel/kernel', '-smp', str(cpus), '-nographic', '-no-reboot'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, bufsize=0)
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.process.stdout, selectors.EVENT_READ)
        self.output = bytearray()

    def expect(self, pattern, start=0, timeout=120):
        deadline = time.monotonic() + timeout
        while True:
            segment = self.output[start:]
            for failure in (b'FAIL:', b'PROCTEST FAIL', b'TEST-4 FAIL'):
                if failure in segment:
                    raise AssertionError(f'guest failure {failure!r}; tail={segment[-16000:]!r}')
            if re.search(rb'panic[:\s]|p\.a\.n\.i\.c\.', segment, re.IGNORECASE):
                raise AssertionError(f'kernel panic; tail={segment[-16000:]!r}')
            if re.search(pattern, segment):
                return
            if pattern != rb'sh> ' and b'sh> ' in segment:
                raise AssertionError(f'shell returned without {pattern!r}; tail={segment[-16000:]!r}')
            if time.monotonic() >= deadline:
                raise AssertionError(f'timeout waiting for {pattern!r}; tail={segment[-16000:]!r}')
            for key, _ in self.selector.select(.1):
                chunk = os.read(key.fd, 65536)
                if not chunk:
                    raise AssertionError(f'QEMU exited ({self.process.poll()}); tail={segment[-16000:]!r}')
                self.output.extend(chunk)

    def command(self, name, patterns, timeout=120):
        start = len(self.output)
        self.process.stdin.write((name + '\n').encode('ascii'))
        self.process.stdin.flush()
        for pattern in patterns:
            self.expect(pattern, start, timeout)
        self.expect(rb'sh> ', start, timeout)
        return bytes(self.output[start:])

    def close(self):
        if self.process.poll() is None:
            self.process.kill()
        self.process.wait()
        self.selector.close()
        self.process.stdin.close()
        self.process.stdout.close()


COMMANDS = {
    'hi': [rb'hi: user program running'],
    'smptest': [rb'RESULT smp_round = 3 workers=8 free_pages=[0-9]+',
                rb'RESULT smp_stress = fork,exec,exit,wait,pause,sbrk,isolation,kill',
                rb'PASS: smptest'],
    'bench': [rb'RESULT avg_fork_wait = [0-9]+',
              rb'RESULT concurrent_children = 8', rb'PASS: bench'],
    'alt': [rb'alt done', rb'PASS: alt'],
    'schedcheck': [rb'PASS: schedcheck'],
    'proctest': [rb'PROCTEST PASS:'],
    'vmtest': [rb'CROSS-PAGE PASS', rb'GUARD PASS', rb'SHRINK PASS',
               rb'EXEC-FAIL PASS', rb'OOM-FORK-EXEC PASS', rb'UNALIGNED-SBRK PASS'],
    'memcap': [rb'TEST-4 PASS: OOM returned error'],
    'badaccess': [rb'TEST-3a PASS', rb'TEST-3b PASS'],
    'pagedump': [rb'DUMP-PAGETABLE begin', rb'DUMP-PAGETABLE end'],
}


def validate_smp(chunk, cpus):
    mask = re.findall(rb'RESULT smp_online = ([0-9]+) reclaimed=([0-9]+)', chunk)
    assert len(mask) == 1 and int(mask[0][0]) == (1 << cpus) - 1, \
        f'wrong online hart mask: {mask!r}'
    counters = re.findall(rb'RESULT smp_hart = ([0-9]+) dispatches=([0-9]+) user_ticks=([0-9]+)', chunk)
    assert len(counters) == cpus and {int(c[0]) for c in counters} == set(range(cpus)), \
        f'missing per-hart user evidence: {counters!r}'
    for hart, dispatches, user_ticks in counters:
        assert int(dispatches) > 0 and int(user_ticks) > 0, \
            f'hart {hart!r} did not execute user processes'
    rounds = re.findall(rb'RESULT smp_round = ([0-9]+) workers=([0-9]+) free_pages=([0-9]+)', chunk)
    assert [int(row[0]) for row in rounds] == [1, 2, 3], rounds
    assert all(int(row[1]) >= 8 for row in rounds), rounds
    assert len({int(row[2]) for row in rounds}) == 1, 'concurrent workload leaked physical pages'
    assert int(mask[0][1]) > int(rounds[-1][2]), 'parent heap pages were not reclaimed'
    clock = re.search(rb'RESULT smp_clock = ticks=([0-9]+) cycles=([0-9]+)', chunk)
    assert clock is not None, 'missing global-clock evidence'
    ticks, cycles = map(int, clock.groups())
    assert ticks >= 20 and 80000 * ticks <= cycles <= 120000 * ticks, \
        f'global clock advanced at the wrong rate: ticks={ticks}, cycles={cycles}'
    return (f'online={int(mask[0][0])}; ' +
            ', '.join(f'hart{int(h)} dispatches={int(d)} user_ticks={int(t)}'
                      for h, d, t in counters) +
            f'; clock={ticks}ticks/{cycles}cycles; reclaimed={int(mask[0][1])}')


def boot_round(number, cpus, evidence, report, serial):
    guest = Guest(cpus)
    banner = pathlib.Path('expect_banner.txt').read_bytes()

    def passed(label):
        line = f'PASS: boot {number} -smp {cpus}: {label}'
        print(line, flush=True)
        report.write(line + '\n')
        report.flush()

    try:
        guest.expect(rb'sh> ', timeout=30)
        assert guest.output.startswith(banner), 'Lab1 banner changed or printed after secondary-hart output'
        assert guest.output.count(banner) == 1, 'boot banner printed more than once'
        passed('one Lab1 banner and interactive shell')
        # Do not apply single-CPU priority ratios to two simultaneously running CPUs.
        plans = [
            ['smptest', 'bench', 'schedcheck', 'proctest', 'hi'],
            ['smptest', 'alt', 'vmtest', 'hi', 'memcap', 'hi'],
            ['smptest', 'schedcheck', 'badaccess', 'pagedump', 'bench', 'hi'],
        ]
        for command in plans[(number - 1) % len(plans)]:
            chunk = guest.command(command, COMMANDS[command], timeout=180)
            detail = ''
            if command == 'smptest':
                detail = '; ' + validate_smp(chunk, cpus)
            elif command == 'alt':
                letters = re.search(rb'\n([AB]+)\nalt done', chunk)
                assert letters is not None, f'alt output damaged: {chunk!r}'
                assert letters[1].count(b'A') == 16 and letters[1].count(b'B') == 16, letters[1]
                assert len(re.findall(rb'A+|B+', letters[1])) > 2, 'alt did not interleave workers'
            elif command == 'pagedump':
                assert b'perm=r-xu' in chunk and b'perm=rw-u' in chunk, chunk
            assert guest.output.count(banner) == 1, 'duplicate global initialization or unexpected reboot'
            passed(command + ' and return to shell' + detail)
        passed('complete concurrent workload and shell recovery')
    finally:
        guest.close()
        raw = bytes(guest.output)
        (evidence / f'smp-boot-{number}-serial.txt').write_bytes(raw)
        serial.write(f'=== boot {number}; qemu -smp {cpus} ===\n'.encode('ascii'))
        serial.write(raw)
        serial.write(b'\n')
        serial.flush()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skip-build', action='store_true')
    parser.add_argument('--rounds', type=int, default=3, help='independent QEMU boots (default: 3)')
    parser.add_argument('--cpus', type=int, choices=(1, 2), default=2)
    parser.add_argument('--evidence-dir', default='labs/lab4/evidence',
                        help='output directory (use a separate path for single-hart compatibility)')
    args = parser.parse_args()
    if args.rounds < 1:
        parser.error('--rounds must be positive')
    root = pathlib.Path(__file__).resolve().parents[1]
    os.chdir(root)
    evidence = root / args.evidence_dir
    evidence.mkdir(parents=True, exist_ok=True)
    with (evidence / 'smp-checks.txt').open('w', encoding='utf-8') as report, \
            (evidence / 'smp-runtime-serial.txt').open('wb') as serial:
        try:
            report.write(f'$ QEMU -smp {args.cpus}; independent_boots={args.rounds}\n')
            if not args.skip_build:
                report.write('$ make\n')
                result = subprocess.run(['make'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                        text=True, encoding='utf-8', errors='replace', timeout=180)
                report.write(result.stdout + f'\nexit={result.returncode}\n')
                report.flush()
                if result.returncode:
                    print(result.stdout, end='')
                    raise AssertionError(f'build failed with exit {result.returncode}')
            for number in range(1, args.rounds + 1):
                boot_round(number, args.cpus, evidence, report, serial)
            line = f'PASS: all Lab4 SMP checks ({args.rounds} boots, {args.cpus} harts)'
            report.write(line + '\n')
            print(line, flush=True)
        except Exception as error:
            report.write('FAIL: ' + str(error) + '\n')
            report.flush()
            raise


if __name__ == '__main__':
    main()
