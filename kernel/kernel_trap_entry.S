    .section .text
    .balign 4
    .globl kernel_trap_entry
kernel_trap_entry:
    # Fatal kernel traps only at this stage: no return or register restoration.
    # Keep the current kernel stack; never overwrite the user's trapframe.
    tail kerneltrap_stop

    .balign 4
    .option norvc
    .globl proc_exit_idle, proc_exit_idle_end
proc_exit_idle:
    # This single-task stage has no next process to schedule after exit.
    wfi
    j proc_exit_idle
proc_exit_idle_end:
