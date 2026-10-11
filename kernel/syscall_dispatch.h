#ifndef SYSCALL_DISPATCH_H
#define SYSCALL_DISPATCH_H

#include "trapframe.h"

uint64 syscall_dispatch(struct trapframe *tf);

#endif
