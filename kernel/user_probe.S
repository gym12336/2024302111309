#include "syscall.h"
    # Our small test program is copied into a U-accessible page at 0x1000.
    # Fixed-width instructions make the observed addresses easy to explain.
    .section .rodata.user_probe,"a"
    .balign 4
    .option norvc
    .option norelax
    .globl user_probe_start, user_probe_done, user_probe_end
user_probe_start:
    ecall
    # Record all 31 restored registers before using any as scratch registers.
    # sp remains 0x4000, so these stores use the last 256 bytes of its page.
    sd ra, -256(sp)
    sd sp, -248(sp)
    sd gp, -240(sp)
    sd tp, -232(sp)
    sd t0, -224(sp)
    sd t1, -216(sp)
    sd t2, -208(sp)
    sd s0, -200(sp)
    sd s1, -192(sp)
    sd a0, -184(sp)
    sd a1, -176(sp)
    sd a2, -168(sp)
    sd a3, -160(sp)
    sd a4, -152(sp)
    sd a5, -144(sp)
    sd a6, -136(sp)
    sd a7, -128(sp)
    sd s2, -120(sp)
    sd s3, -112(sp)
    sd s4, -104(sp)
    sd s5, -96(sp)
    sd s6, -88(sp)
    sd s7, -80(sp)
    sd s8, -72(sp)
    sd s9, -64(sp)
    sd s10, -56(sp)
    sd s11, -48(sp)
    sd t3, -40(sp)
    sd t4, -32(sp)
    sd t5, -24(sp)
    sd t6, -16(sp)
    # After the original full-register snapshot, exercise dispatch boundaries.
    .globl user_probe_getpid_first, user_probe_wide, user_probe_zero
    .globl user_probe_unimplemented, user_probe_getpid_last
    li a7, SYS_getpid
user_probe_getpid_first:
    ecall
    sd a0, -512(sp)
    li a7, 0x10000000b         # Low 32 bits equal 11, but this is not getpid.
user_probe_wide:
    ecall
    sd a0, -504(sp)
    li a7, 0
user_probe_zero:
    ecall
    sd a0, -496(sp)
    li a7, SYS_write           # Defined in the contract, not implemented yet.
user_probe_unimplemented:
    ecall
    sd a0, -488(sp)
    li a7, SYS_getpid
user_probe_getpid_last:
    ecall
    sd a0, -480(sp)
    li t0, 0x3ff8
    li t1, 0x50415353          # "PASS": published after all register stores
    sd t1, 0(t0)
user_probe_done:
    j user_probe_done         # Do not use privileged wfi in the user test.
user_probe_end:
