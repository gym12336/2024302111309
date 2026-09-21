#include "course_sid.h"

    .section .text
    .globl _entry
_entry:
    # Keep the early boot sequence from being interrupted.
    csrci mstatus, 8
    csrw mie, zero

    # Give unexpected M-mode traps a known, correctly aligned destination.
    la t0, m_trap_vector
    csrw mtvec, t0

    # This lab boots on hart 0 only. Other harts wait here forever.
    csrr t0, mhartid
    bnez t0, park

    # The stack grows downward, so start at the first byte above its storage.
    la sp, boot_stack_top

    call start

    # start() should leave M-mode with mret and must never return.
park:
    wfi
    j park

    .balign 4
m_trap_vector:
    wfi
    j m_trap_vector

    .section .bss
    .balign 16
boot_stack:
    .space LAB1_STACK_KB * 1024
boot_stack_top:
