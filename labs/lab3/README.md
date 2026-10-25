# Lab3：三级页表与物理内存管理

说明书：`lab3-实验说明书-学生版-V3.1.docx`。

完整逐文件讲解、设计决策、问答与现场演示步骤见 [Lab3逐文件答辩讲解与演示.md](Lab3逐文件答辩讲解与演示.md)。其中第四至第九节同时作为本次实验设计笔记，记录分配器结构、回滚所有权、保护区、TLB、PCB 生命周期和用户指针审查。

在工程根目录的 Ubuntu/WSL 终端中：

```bash
make
python3 tools/run_lab3_checks.py
make qemu
```

QEMU 的 `sh> ` 中依次输入：

```text
pagedump
badaccess
vmtest
memcap
hi
proctest
vmconcurrent
hi
```

最后一项启动持续运行的 spin；结束演示用 `Ctrl+A` 后按 `X` 退出 QEMU。四进程槽、无文件系统、exec 暂不装载 argv，保留当前教学阶段边界。

`tools/run_lab3_checks.py` 保存构建与检查结果到 `evidence/checks.txt`，实际串口输出到 `evidence/runtime-serial.txt`，串口回归到 `evidence/lab2-*.txt`。测试使用独立探针镜像验证分配器和中途 OOM，不替换正式 `kernel/kernel`。

主要完成项：降序位图物理页管理；4KB 三级 walk/映射/回滚/拆映射；完整内核 RAM 与外设映射；用户代码 RX、数据 RW、两页无映射保护区；按页受控拷贝；EAGER sbrk；fork 深拷贝与 exec 成功后替换；trapframe/内核栈延后回收；ABI 页表输出与现场重放；用于并发验收的最小用户态轮转。

配置保持 `LAB3_ALLOC_ORDER=1`、`LAB3_GUARD_PAGES=2`、`LAB3_MEMCAP_DELTA=13`。未采用高地址 KSTACK 映射；内核栈使用 RAM 恒等映射。时钟通过 CSR，不需要 CLINT MMIO 映射。内核 RAM 的统一 RWX 为本阶段允许的过渡设计，用户代码没有 W。
