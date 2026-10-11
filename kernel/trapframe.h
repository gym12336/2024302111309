#ifndef TRAPFRAME_H
#define TRAPFRAME_H

#include "types.h"

// Memory contract with the immutable course trampoline.S. All offsets are bytes.
struct trapframe {
  uint64 kernel_satp;   //   0: kernel page-table control value
  uint64 kernel_sp;     //   8: kernel stack top
  uint64 kernel_trap;   //  16: usertrap C entry
  uint64 epc;           //  24: user instruction address, managed by C
  uint64 kernel_hartid; //  32: kernel hardware-thread identifier
  uint64 ra;           //  40
  uint64 sp;           //  48
  uint64 gp;           //  56
  uint64 tp;           //  64
  uint64 t0;           //  72
  uint64 t1;           //  80
  uint64 t2;           //  88
  uint64 s0;           //  96
  uint64 s1;           // 104
  uint64 a0;           // 112
  uint64 a1;           // 120
  uint64 a2;           // 128
  uint64 a3;           // 136
  uint64 a4;           // 144
  uint64 a5;           // 152
  uint64 a6;           // 160
  uint64 a7;           // 168
  uint64 s2;           // 176
  uint64 s3;           // 184
  uint64 s4;           // 192
  uint64 s5;           // 200
  uint64 s6;           // 208
  uint64 s7;           // 216
  uint64 s8;           // 224
  uint64 s9;           // 232
  uint64 s10;          // 240
  uint64 s11;          // 248
  uint64 t3;           // 256
  uint64 t4;           // 264
  uint64 t5;           // 272
  uint64 t6;           // 280
};

// GNU C accepts these compiler assertions with the project's gnu99 flags.
#define TF_CHECK_OFFSET(field, expected) \
  _Static_assert(__builtin_offsetof(struct trapframe, field) == (expected), \
                 "trapframe offset mismatch: " #field)

TF_CHECK_OFFSET(kernel_satp, 0);
TF_CHECK_OFFSET(kernel_sp, 8);
TF_CHECK_OFFSET(kernel_trap, 16);
TF_CHECK_OFFSET(epc, 24);
TF_CHECK_OFFSET(kernel_hartid, 32);
TF_CHECK_OFFSET(ra, 40);
TF_CHECK_OFFSET(sp, 48);
TF_CHECK_OFFSET(gp, 56);
TF_CHECK_OFFSET(tp, 64);
TF_CHECK_OFFSET(t0, 72);
TF_CHECK_OFFSET(t1, 80);
TF_CHECK_OFFSET(t2, 88);
TF_CHECK_OFFSET(s0, 96);
TF_CHECK_OFFSET(s1, 104);
TF_CHECK_OFFSET(a0, 112);
TF_CHECK_OFFSET(a1, 120);
TF_CHECK_OFFSET(a2, 128);
TF_CHECK_OFFSET(a3, 136);
TF_CHECK_OFFSET(a4, 144);
TF_CHECK_OFFSET(a5, 152);
TF_CHECK_OFFSET(a6, 160);
TF_CHECK_OFFSET(a7, 168);
TF_CHECK_OFFSET(s2, 176);
TF_CHECK_OFFSET(s3, 184);
TF_CHECK_OFFSET(s4, 192);
TF_CHECK_OFFSET(s5, 200);
TF_CHECK_OFFSET(s6, 208);
TF_CHECK_OFFSET(s7, 216);
TF_CHECK_OFFSET(s8, 224);
TF_CHECK_OFFSET(s9, 232);
TF_CHECK_OFFSET(s10, 240);
TF_CHECK_OFFSET(s11, 248);
TF_CHECK_OFFSET(t3, 256);
TF_CHECK_OFFSET(t4, 264);
TF_CHECK_OFFSET(t5, 272);
TF_CHECK_OFFSET(t6, 280);
_Static_assert(sizeof(struct trapframe) == 288, "trapframe must be 288 bytes");

#undef TF_CHECK_OFFSET

#endif
