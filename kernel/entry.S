#include "course_sid.h"
#include "param.h"

    .section .text
    .globl _entry
_entry:
    # Keep the early boot sequence from being interrupted.
    csrci mstatus, 8
    csrw mie, zero

    # Give unexpected M-mode traps a known, correctly aligned destination.
    la t0, m_trap_vector
    csrw mtvec, t0

    # Each hart gets its own boot stack and keeps its ID in kernel tp.
    csrr t0, mhartid
    li t1, NCPU
    bgeu t0, t1, park
    mv tp, t0
    la sp, boot_stack
    addi t0, t0, 1
    li t1, LAB1_STACK_KB * 1024
    mul t0, t0, t1
    add sp, sp, t0

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
    .space NCPU * LAB1_STACK_KB * 1024
boot_stack_top:
