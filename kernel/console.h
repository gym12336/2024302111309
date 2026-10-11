#ifndef CONSOLE_H
#define CONSOLE_H

// Input is byte-oriented; -1 from console_getc means no committed byte.
void console_input(int c);
int console_getc(void);

#endif
