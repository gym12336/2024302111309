#!/usr/bin/env python3
"""Reproduce Lab3 acceptance; keep all evidence under labs/lab3/evidence."""
import os
import pathlib
import subprocess
import sys


def main():
    root = pathlib.Path(__file__).resolve().parents[1]
    os.chdir(root)
    evidence = root/'labs/lab3/evidence'
    evidence.mkdir(exist_ok=True)
    commands = [['make'], [sys.executable, 'tools/check_lab3_support.py'],
                [sys.executable, 'tools/check_lab3_vm.py'],
                [sys.executable, 'tools/check_lab3_runtime.py']]
    for stem in ['lab2-stream', 'lab2-long-storm']:
        commands.append([sys.executable, 'tools/run_course_inject.py', '--tree', '.',
                         '--script', f'support/{stem}.txt',
                         '--log', f'labs/lab3/evidence/{stem}.txt'])
    with (evidence/'checks.txt').open('w', encoding='utf-8') as log:
        for command in commands:
            label = '$ '+' '.join(command)
            print(label, flush=True)
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, timeout=180)
            log.write(label+'\n'+result.stdout+f'exit={result.returncode}\n\n')
            log.flush()
            print(result.stdout, end='', flush=True)
            if result.returncode:
                raise SystemExit(result.returncode)
        log.write('PASS: all Lab3 acceptance checks passed\n')
    print('PASS: all Lab3 acceptance checks passed')


if __name__ == '__main__':
    main()
