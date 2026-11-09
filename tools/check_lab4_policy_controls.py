#!/usr/bin/env python3
"""Build isolated RR/no-aging controls and verify the ID9 test rejects both."""
import hashlib
import os
import pathlib
import re
import selectors
import subprocess
import tempfile
import time


class Serial:
    def __init__(self, kernel):
        self.process = subprocess.Popen(
            ['qemu-system-riscv64', '-machine', 'virt', '-bios', 'none',
             '-kernel', str(kernel), '-smp', '1', '-nographic'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, bufsize=0)
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.process.stdout, selectors.EVENT_READ)
        self.output = bytearray()

    def prompt(self, start=0, timeout=30):
        end = time.monotonic() + timeout
        while b'sh> ' not in self.output[start:]:
            segment = self.output[start:]
            if b'panic:' in segment.lower() or b'p.a.n.i.c.' in segment.lower():
                raise AssertionError(f'control kernel panicked: {segment!r}')
            if time.monotonic() >= end:
                raise AssertionError(f'control did not return to shell: {segment!r}')
            for key, _ in self.selector.select(.1):
                data = os.read(key.fd, 65536)
                if not data:
                    raise AssertionError('control kernel exited')
                self.output.extend(data)

    def command(self, name):
        start = len(self.output)
        self.process.stdin.write((name + '\n').encode())
        self.process.stdin.flush()
        self.prompt(start)
        return bytes(self.output[start:])

    def close(self):
        self.process.kill()
        self.process.wait()
        self.selector.close()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    root = pathlib.Path(__file__).resolve().parents[1]
    os.chdir(root)
    evidence = root / 'labs/lab4/evidence'
    evidence.mkdir(parents=True, exist_ok=True)
    formal = [pathlib.Path(name) for name in
              ('kernel/proc.c', 'kernel/proc.o', 'kernel/kernel')]
    before = {str(path): digest(path) for path in formal}
    source = formal[0].read_text()
    predicate = '(!best || p->priority > best_priority)'
    assert source.count(predicate) == 1, 'scheduler predicate changed'
    rr = source.replace(predicate, '(!best)')
    rr = rr.replace('int chosen = -1, best_priority = -1;', 'int chosen = -1;')
    rr = rr.replace('        best_priority = p->priority;\n', '')
    aging = 'p->state == PROC_RUNNABLE && p->priority == 0 && ++p->ready_ticks >= 8'
    assert source.count(aging) == 1, 'aging predicate changed'
    no_aging = source.replace(aging, '0 && (' + aging + ')')
    flags = ['-Wall', '-Werror', '-O', '-std=gnu99', '-mcmodel=medany',
             '-ffreestanding', '-nostdlib', '-fno-common', '-ggdb',
             '-march=rv64gc', '-fno-stack-protector', '-fno-pie', '-Ikernel']
    objects = subprocess.check_output(
        ['make', '-s', '--no-print-directory', '--eval',
         'lab4-print-objects:;@echo $(OBJS)', 'lab4-print-objects'], text=True).strip().split()
    with (evidence / 'policy-controls.txt').open('w', encoding='utf-8') as log:
        log.write('Lab4 single-hart policy control experiments\n'
                  'Each control compiles a temporary proc.c and links its temporary proc.o\n'
                  'in place of kernel/proc.o. Formal sources, objects and image stay untouched.\n'
                  'Only policy selection changes; swtch, locks, timer, sleep and wait are shared.\n\n')
        with tempfile.TemporaryDirectory(prefix='lab4-policy-controls-') as folder:
            folder = pathlib.Path(folder)
            for name, text in [('round-robin', rr), ('no-aging', no_aging)]:
                mutant, obj, kernel = (folder / (name + suffix)
                                       for suffix in ('.c', '.o', '.elf'))
                mutant.write_text(text)
                compile_command = ['riscv64-unknown-elf-gcc', *flags, '-c', str(mutant), '-o', str(obj)]
                link_command = ['riscv64-unknown-elf-ld', '-T', 'kernel/kernel.ld', '-o', str(kernel),
                                *[str(obj) if item == 'kernel/proc.o' else item for item in objects]]
                log.write(f'CONTROL {name}\n')
                if name == 'round-robin':
                    log.write('Mutation: scheduler selects the first RUNNABLE process after rr_idx; ignores priority.\n')
                else:
                    log.write('Mutation: disable proc_clock READY-wait aging; keep priority selection.\n')
                for command in (compile_command, link_command):
                    log.write('$ ' + ' '.join(command) + '\n')
                    result = subprocess.run(command, capture_output=True, text=True, timeout=30)
                    log.write(result.stdout + result.stderr)
                    assert result.returncode == 0, result.stderr
                serial = Serial(kernel)
                try:
                    serial.prompt()
                    if name == 'round-robin':
                        output = serial.command('bench')
                        assert b'PASS: bench' in output and b'RESULT concurrent_children = 8' in output, output
                        print('PASS: RR control bench mechanism', flush=True)
                        output = serial.command('alt')
                        letters = re.search(rb'\n([AB]+)\nalt done', output)
                        assert b'PASS: alt' in output and letters is not None, output
                        letters = letters.group(1)
                        assert letters.count(b'A') == 16 and letters.count(b'B') == 16, output
                        assert len(re.findall(rb'A+|B+', letters)) > 2, output
                        print('PASS: RR control timer preemption and alternating children', flush=True)
                    output = serial.command('priority_test')
                    expected = (b'FAIL: priority priority boundary missing' if name == 'round-robin'
                                else b'FAIL: priority low priority starved')
                    assert expected in output and b'PASS: priority ID9' not in output, output
                    log.write(serial.output.decode('utf-8', errors='replace') + '\n')
                    log.write('EXPECTED REJECTION: ' + expected.decode() + '\n\n')
                    print(f'PASS: priority_test rejects {name} control', flush=True)
                finally:
                    serial.close()
        after = {str(path): digest(path) for path in formal}
        assert after == before, 'formal source, object or image changed during controls'
        for path, value in after.items():
            log.write(f'UNCHANGED SHA256 {path} {value}\n')
        log.write('PASS: RR mechanism works; ID9 observation rejects RR and starvation without aging.\n')
        print('PASS: all policy controls; formal source/object/kernel hashes unchanged', flush=True)


if __name__ == '__main__':
    main()
