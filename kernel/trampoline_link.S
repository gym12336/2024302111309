// The course trampoline declares trampsec without ELF load/execute flags.
// Declare the section first, then include the unmodified gift source.
    .section trampsec,"ax"
#include "trampoline.S"
