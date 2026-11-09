# Lab4 进程上下文切换与调度策略

本实验在 Lab3 工程上加入真实内核上下文切换、每进程锁、时钟抢占和标准休眠唤醒，个人策略为学号 `2024302111309`对应的 **ID9 两级优先级加 8 tick 老化**，验收基线为单核。

- [完整调用图与操作系统作用讲解](Lab4完整调用图与操作系统作用讲解.md)：按四阶段串起实验要求、代码和运行过程，建议从这里阅读。
- [设计笔记](设计笔记.md)：起点差距、锁顺序、上下文 ABI、策略决策与丢失唤醒分析。
- [自测用例](自测用例.md)：两项策略用例、机制与回归检查、观测数据的解释。
- [课程实验说明书](lab4-实验说明书-学生版-V3.docx)和[能力目标与接口约定](能力目标与接口约定.md)：核对原始要求。

在 WSL 中进入工程根目录，执行：

```bash
python3 tools/run_lab4_checks.py
make qemu
```

自动验收结果保存在 [checks.txt](evidence/checks.txt)，原始串口在 [runtime-serial.txt](evidence/runtime-serial.txt)，课程注入器回归在 [uart-regression.txt](evidence/uart-regression.txt)。以实际证据中的退出码、`PASS/FAIL`和观测值为准。

最终清理后重建与主验收通过：bench回收8孩子，高低CPU采样48:12，低孩子两个CPU tick加老化恢复11tick，同级22:22，6条UART EXPECT均通过。采样数值随运行可变化。

独立回归及反例检查命令：

```bash
python3 tools/check_lab4_vm_regression.py
python3 tools/check_exit.py
python3 tools/check_lab3_vm.py
python3 tools/check_lab4_lost_wakeup.py
python3 tools/check_lab4_policy_controls.py
```

- [Lab3运行回归](evidence/vm-regression.txt)及[串口](evidence/vm-regression-serial.txt)：页表、用户内存、fork/exec、重复OOM、spin/shell并发通过。
- [旧探针回归](evidence/probe-regression.txt)：31寄存器与退出码7、0、-3通过。
- [分配器与页表回滚](evidence/allocator-vm.txt)：分配、OOM和资源守恒通过。
- [课程支撑件检查](evidence/support-checks.txt)：预置文件完整性、跳板AX/对齐与依赖通过。
- [丢失唤醒反例](evidence/lost-wakeup.txt)：隔离故障镜像复现bench首轮阻塞，正式源码与镜像未替换。
- [策略对照](evidence/policy-controls.txt)：轮转32:32、无老化60:0均被策略测试正确拒绝，正式文件SHA256不变。

手工演示依次输入 `hi`、`pagedump`、`badaccess`、`bench`、`alt`、`schedcheck`、`priority_test`。有限程序结束应恢复 `sh> `，退出 QEMU 按 Ctrl+a 后按 x。

Lab4 课程调用号23～25保持原意；本地 `setpriority`使用26，Lab3本地页表调用迁移到27以避开23号冲突。课程彩票与步长测试已接入构建，ID9用自写 `priority_test`进行策略验收。
