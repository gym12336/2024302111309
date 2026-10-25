#!/usr/bin/env python3
"""Run real allocator initialization in isolated RISC-V probe kernels."""
import os
import pathlib
import selectors
import subprocess
import tempfile
import time


PROBE = r'''
#include "kalloc.c"

static void emit(const char *text)
{
  volatile uint8 *uart = (volatile uint8 *)UART0;
  while (*text) {
    while (!(uart[5] & (1 << 5))) {}
    uart[0] = *text++;
  }
}

static void require(int condition)
{
  if (!condition) {
    emit("KINIT FAIL\n");
    for (;;) asm volatile("wfi");
  }
}

void main(void)
{
  struct kalloc_stats info;
  require(kalloc_get_stats(&info) == -1);
  require(kinit() == 0);
  require(kalloc_get_stats(0) == -1);
  require(kalloc_get_stats(&info) == 0);
  require(info.first_pa == PGROUNDUP((uint64)kernel_end));
  require(info.limit_pa == PHYSTOP - 13UL * PGSIZE);
  require(info.first_pa % PGSIZE == 0 && info.limit_pa % PGSIZE == 0);
  require(info.total_pages == (info.limit_pa - info.first_pa) / PGSIZE);
  require(info.free_pages == info.total_pages && info.total_pages > 0);
  uint64 bits = 0;
  for (uint64 page = 0; page < RAM_PAGES; page++) {
    uint64 pa = KERNBASE + page * PGSIZE;
    int free = !!(kmem.free_bitmap[page / 64] & (1UL << (page % 64)));
    require(free == (pa >= info.first_pa && pa < info.limit_pa));
    bits += free;
  }
  require(bits == info.free_pages);
  require(kmem.search_word == ((info.limit_pa - PGSIZE - KERNBASE) / PGSIZE) / 64);
  // A second init may not destroy the bitmap, counters, or future allocations.
  uint64 word = kmem.search_word;
  uint64 saved = kmem.free_bitmap[word];
  kmem.free_bitmap[word] = 0;
  require(kinit() == -1 && kmem.free_bitmap[word] == 0);
  kmem.free_bitmap[word] = saved;
  emit("KINIT PASS: range, all bitmap bits, 13 reserved pages, counts, reinit\n");
  for (;;) asm volatile("wfi");
}
'''


def run_case(root, folder, padding):
    source = folder / "probe.c"
    # Real BSS padding moves kernel_end; the allocator must not use a fixed base.
    source.write_text(PROBE + f'\nuint8 image_padding[{padding}];\n')
    flags = ["-Wall", "-Werror", "-O", "-std=gnu99", "-mcmodel=medany",
             "-ffreestanding", "-nostdlib", "-fno-common", "-march=rv64gc",
             "-fno-stack-protector", "-fno-pie", "-Ikernel"]
    objects = []
    for name, path in (("entry", root / "kernel/entry.S"),
                       ("start", root / "kernel/start.c"), ("probe", source)):
        obj = folder / (name + ".o")
        subprocess.run(["riscv64-unknown-elf-gcc", *flags, "-c", str(path),
                        "-o", str(obj)], check=True)
        objects.append(str(obj))
    kernel = folder / "probe.elf"
    subprocess.run(["riscv64-unknown-elf-ld", "-T", "kernel/kernel.ld", "-o",
                    str(kernel), *objects], check=True)
    process = subprocess.Popen([
        "qemu-system-riscv64", "-machine", "virt", "-bios", "none",
        "-kernel", str(kernel), "-m", "128M", "-smp", "1", "-display", "none",
        "-serial", "stdio", "-monitor", "none"], stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    try:
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        output = bytearray()
        deadline = time.monotonic() + 15
        while b"KINIT PASS: range, all bitmap bits, 13 reserved pages, counts, reinit\n" not in output:
            if time.monotonic() > deadline:
                raise RuntimeError(f"probe timeout: {output!r}")
            for key, _ in selector.select(0.2):
                chunk = os.read(key.fd, 4096)
                if not chunk:
                    raise RuntimeError(f"probe exited early: {output!r}")
                output.extend(chunk)
            if b"KINIT FAIL" in output:
                raise RuntimeError(output.decode(errors="replace"))
        print(f"PASS: image padding={padding}; " + output.decode().strip(), flush=True)
    finally:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        process.stdout.close()
        selector.close()


def main():
    root = pathlib.Path(__file__).resolve().parents[1]
    os.chdir(root)
    with tempfile.TemporaryDirectory(prefix="lab3-kinit-") as directory:
        for padding in (1, 5001):
            folder = pathlib.Path(directory) / str(padding)
            folder.mkdir()
            run_case(root, folder, padding)
    print("PASS: initialization probes did not replace or enable the formal allocator")


if __name__ == "__main__":
    main()
