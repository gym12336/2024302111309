#ifndef UART_H
#define UART_H

void uart_init(void);
int uartgetc(void);
void uartintr(void);
void uartputc_sync(int c);

#endif
