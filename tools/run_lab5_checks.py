#!/usr/bin/env python3
"""Run Lab5 acceptance and the earlier lab regressions in QEMU under WSL."""
import argparse
import os
import pathlib
import re
import shlex
import subprocess
import sys

from run_lab4_smp_checks import COMMANDS, Guest, validate_smp


COPY_COUNTS = rb'T5-1 copies: ([0-9]+) -> ([0-9]+) \(delta ([0-9]+)\)'
COW_PAIR = rb'T5-2 copies delta = 2 \(expect 2\)'
BUDGET_WARNING = rb'COW budget reached: pid=[0-9]+ copies=([0-9]+); continuing'
BUDGET_PASS = rb'COWTEST PASS: budget ([0-9]+), [0-9]+ heap pages written, [0-9]+ copies'
MEMCAP = rb'TEST-4 PASS: OOM returned error after ([0-9]+) chunks'


def run_logged(command, report, timeout):
    report.write('$ ' + shlex.join(command) + '\n')
    report.flush()
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding='utf-8', errors='replace', timeout=timeout)
    report.write(result.stdout + f'\nexit={result.returncode}\n')
    report.flush()
    if result.returncode:
        print(result.stdout, end='', flush=True)
        result.check_returncode()


def passed(label, report):
    line = 'PASS: ' + label
    print(line, flush=True)
    report.write(line + '\n')
    report.flush()


def check_guest(cpus, evidence, report):
    guest = Guest(cpus)
    try:
        guest.expect(rb'LAB5 kref_selftest PASS', timeout=30)
        guest.expect(rb'sh> ', timeout=30)
        banner = pathlib.Path('expect_banner.txt').read_bytes()
        assert guest.output.startswith(banner), 'Lab1 banner changed'
        passed(f'{cpus} CPU boot, reference-count self-test and shell', report)

        zerocopy = guest.command('zerocopy', [COPY_COUNTS, rb'T5-1 PASS'])
        before, after, delta = map(int, re.search(COPY_COUNTS, zerocopy).groups())
        assert after - before == delta <= 2, zerocopy
        passed(f'{cpus} CPU zerocopy, {delta} page copies', report)

        rounds = 1 if cpus == 1 else 5
        for _ in range(rounds):
            cowpair = guest.command('cowpair', [COW_PAIR, rb'T5-2 PASS'])
            assert b'T5-2 WARN' not in cowpair, cowpair
        passed(f'{cpus} CPU cowpair, exactly 2 copies in each of {rounds} runs', report)

        guest.command('echo hi', [rb'(?:^|\n)hi\r?\nT5-3 PASS: argc=2 argv\[0\]=echo aligned'])
        passed(f'{cpus} CPU echo hi, aligned argv and NULL sentinel', report)

        cowtest = guest.command('cowtest', [BUDGET_PASS, rb'COWTEST PASS: all five checks'])
        budget = re.search(BUDGET_PASS, cowtest)[1]
        assert re.findall(BUDGET_WARNING, cowtest) == [budget], cowtest
        passed(f'{cpus} CPU cowtest, all five checks and one budget warning at {int(budget)} copies', report)

        if cpus == 2:
            result = guest.command('smptest', COMMANDS['smptest'])
            passed(f'2 CPU smptest, {validate_smp(result, cpus)}', report)
        else:
            for name in ('bench', 'badaccess', 'vmtest'):
                guest.command(name, COMMANDS[name])
                passed(f'{name} regression and shell recovery', report)
            chunks = [re.search(MEMCAP, guest.command('memcap', [MEMCAP]))[1] for _ in range(2)]
            assert chunks[0] == chunks[1] and int(chunks[0]) > 0, chunks
            passed(f'memcap regression reached {int(chunks[0])} chunks on both runs', report)
            guest.command('priority_test', [rb'PASS: priority ID9'])
            passed('Lab4 setpriority regression and shell recovery', report)

        guest.command('hi', COMMANDS['hi'])
        assert guest.output.count(banner) == 1, 'unexpected guest reboot'
    finally:
        guest.close()
        (evidence / f'runtime-serial-{cpus}cpu.txt').write_bytes(guest.output)


def check_uart(evidence, report):
    # Lab4's stream plan accounts for the larger process table and hence different PIDs.
    plans = {
        'stream': 'labs/lab4/uart-regression.txt',
        'long-storm': 'support/lab2-long-storm.txt',
    }
    for name, plan in plans.items():
        log = evidence / f'uart-{name}.txt'
        run_logged([sys.executable, 'tools/run_course_inject.py', '--tree', '.',
                    '--script', plan, '--log', str(log)], report, timeout=120)
        if name == 'stream':
            assert log.read_bytes().count(b'hi: user program running, pid=') >= 2, \
                'Shell failed to run hi after the UART regression workload'
        passed(f'Lab2 UART {name}', report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence-dir', default='labs/lab5/evidence')
    parser.add_argument('--skip-build', action='store_true')
    args = parser.parse_args()
    root = pathlib.Path(__file__).resolve().parents[1]
    os.chdir(root)
    evidence = root / args.evidence_dir
    evidence.mkdir(parents=True, exist_ok=True)
    with (evidence / 'checks.txt').open('w', encoding='utf-8') as report:
        try:
            if not args.skip_build:
                run_logged(['make'], report, timeout=180)
                passed('kernel build', report)
            for cpus in (1, 2):
                check_guest(cpus, evidence, report)
            check_uart(evidence, report)
            passed('all Lab5 acceptance checks and regressions', report)
        except Exception as error:
            report.write(f'FAIL: {error}\n')
            raise


if __name__ == '__main__':
    main()
