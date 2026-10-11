#ifndef TRAP_H
#define TRAP_H

#include "types.h"

void trap_init(void);
void usertrap(void) __attribute__((noreturn));
void usertrapret(uint64 user_satp) __attribute__((noreturn));
void kerneltrap_stop(void) __attribute__((noreturn));

#endif
