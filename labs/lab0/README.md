# lab0 交付物(热身实验,通过制不计分)

lab1 验收时教师会随机抽验这三份材料,请把成品放在本目录。

本目录现有 3 份配套讲解与 5 张 SVG 图：材料一 1 张、材料二 3 张、材料三 1 张。图纸对照本机 `lab0/xv6-riscv` 参考树重新核对；其中进程表与文件表是单核、无重定向的一次典型快照，不把运行时分配的指针当成固定常数。运行 `python3 labs/lab0/render_figs.py` 可重新生成五张图。

## 材料一:全系统控制流图(模块级)

追踪 shell 执行 `echo hi` 的全生命周期,从敲回车到屏幕显示 `hi`。

骨干节点:
- Shell: `read` → 阻塞等待 → (UART 中断) → `fork` → `exec(echo)` → `wait`
- 内核: `usertrap` → `syscall` 分发 → … → `scheduler` → … → uart 驱动输出
- echo: `main` → `write(1,"hi")` → `exit`

每个阶段必须标注:当前栈(用户栈 / 该进程内核栈 / 调度器专门栈)、特权级(U/S/M)、是否持有自旋锁。

## 材料二:核心数据结构全景快照

截面时刻:exec 刚执行完,echo 的首条用户指令尚未运行。

1. 进程表快照 — shell / echo / init 的 `state`、`parent`、`pagetable`、`sz`、`ofile[]`
2. 页表快照 — echo 的完整映射树:trampoline、trapframe、代码段、用户栈、guard page、堆区,标明虚拟地址区间与 PTE 权限位
3. 文件表快照 — `ofile[]` → `struct file` → inode 对 stdout 的引用链路

## 材料三:一次时钟中断的微观旅程

`scause = 0x8000000000000005` 进入 `usertrap` 到 `sret` 返回用户态之间的全部动作,含 `yield` 与调度决策。

## 检查清单

- [ ] 控制流图完整覆盖 read → fork → exec → write → exit
- [ ] 核心跳转标注了堆栈归属与特权级转换
- [ ] 三张快照字段完整,引用链路清晰(file → inode,proc → pagetable)
- [ ] 页表快照标出 trampoline 与 trapframe 的虚拟地址边界及权限位
- [ ] 时钟中断流程体现寄存器现场保护、调度器交接与 sret 恢复
- [ ] 图纸含至少 3 处自主思考批注(疑问点 / 边界特例 / 启发点)

## 阅读对象

MIT xv6-riscv 源码。注意新版上游命名:`usertrapret` 已改名 `prepare_return`,`sleep` 拆为两段式(`sleep_prepare`)——以树内实际命名为准。

参考书:[../../docs/lab0/xv6-book-riscv-rev5.pdf](../../docs/lab0/xv6-book-riscv-rev5.pdf),重点《Operating system interfaces》《Traps and system calls》两章。
