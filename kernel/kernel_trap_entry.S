    .section .text
    .balign 4
    .globl kernel_trap_entry
kernel_trap_entry:
    # Fatal kernel traps only at this stage: no return or register restoration.
    # Keep the current kernel stack; never overwrite the user's trapframe.
    tail kerneltrap_stop
