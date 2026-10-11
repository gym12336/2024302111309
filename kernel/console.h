#ifndef CONSOLE_H
#define CONSOLE_H

#include "types.h"

// Input is byte-oriented; -1 from console_getc means no committed byte.
void console_input(int c);
int console_getc(void);
int console_read(uint64 *pagetable, uint64 destination, uint64 length);

#endif
