#include <stdarg.h>

#include "types.h"

extern void putchar(int c);

static void
print_unsigned(uint64 value, uint base)
{
  static const char digits[] = "0123456789abcdef";
  char buffer[32];
  int length = 0;

  do {
    buffer[length++] = digits[value % base];
    value /= base;
  } while (value != 0);

  while (length > 0)
    putchar(buffer[--length]);
}

static void
print_signed(long value)
{
  uint64 magnitude;

  if (value < 0) {
    putchar('-');
    magnitude = (uint64)(-(value + 1)) + 1;
  } else {
    magnitude = (uint64)value;
  }

  print_unsigned(magnitude, 10);
}

static void
print_string(const char *text)
{
  if (text == 0)
    text = "(null)";

  while (*text != '\0')
    putchar(*text++);
}

void
printf(const char *format, ...)
{
  va_list arguments;
  va_start(arguments, format);

  while (*format != '\0') {
    if (*format != '%') {
      putchar(*format++);
      continue;
    }

    format++;
    if (*format == '\0') {
      putchar('%');
      break;
    }

    if (*format == 'l') {
      format++;
      if (*format == 'd')
        print_signed(va_arg(arguments, long));
      else if (*format == 'u')
        print_unsigned(va_arg(arguments, unsigned long), 10);
      else if (*format == 'x')
        print_unsigned(va_arg(arguments, unsigned long), 16);
      else {
        putchar('%');
        putchar('l');
        if (*format != '\0')
          putchar(*format);
      }

      if (*format != '\0')
        format++;
      continue;
    }

    switch (*format) {
    case 'c':
      putchar(va_arg(arguments, int));
      break;
    case 's':
      print_string(va_arg(arguments, const char *));
      break;
    case 'd':
      print_signed((long)va_arg(arguments, int));
      break;
    case 'u':
      print_unsigned((uint64)va_arg(arguments, unsigned int), 10);
      break;
    case 'x':
      print_unsigned((uint64)va_arg(arguments, unsigned int), 16);
      break;
    case '%':
      putchar('%');
      break;
    default:
      putchar('%');
      putchar(*format);
      break;
    }
    format++;
  }

  va_end(arguments);
}
