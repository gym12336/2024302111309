#ifndef USER_MEM_H
#define USER_MEM_H

#include "types.h"

int user_readable(uint64 *pagetable, uint64 address, uint64 length);
int user_copyin(uint64 *pagetable, void *destination, uint64 source, uint64 length);
// Validate the whole range and resolve writable COW mappings before use.
int user_writable(uint64 *pagetable, uint64 address, uint64 length);
int user_copyout(uint64 *pagetable, uint64 destination, const void *source, uint64 length);

#endif
