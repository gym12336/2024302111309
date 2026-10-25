# Lab3 逐文件答辩讲解与演示

对应：`lab3-实验说明书-学生版-V3.1.docx`；学号：2024302111309。

本文按照“先演示结果，再对照文件解释实现”的顺序组织。代码位置用函数名定位：在 IDE 中按 `Ctrl+F` 搜索函数名，比记住会随修改变化的行号可靠。所有命令均针对本工程，不需要切换到旁边的其他 xv6 目录。

## 一、先准备终端，区分两种命令环境

### 1. 在 Windows PowerShell 中进入工程并启动 Ubuntu

```powershell
cd 'D:\UserFolders\Desktop\osshijian\2024302111309高一鸣'
wsl -d Ubuntu
```

进入 WSL 后，如果当前目录没有自动保留，再执行：

```bash
cd '/mnt/d/UserFolders/Desktop/osshijian/2024302111309高一鸣'
```

下面带 `make`、`python3`、`riscv64-unknown-elf-*` 的命令都在 Ubuntu 终端执行。看到 `sh> ` 后，只能输入本实验内核包含的用户程序名称，不能把 Linux 命令输入进去。

### 2. 编译和自动验证

```bash
make
python3 tools/check_lab3_support.py
python3 tools/check_lab3_vm.py
python3 tools/check_lab3_runtime.py
python3 tools/run_course_inject.py --tree . --script support/lab2-stream.txt --log labs/lab3/evidence/lab2-stream.txt
python3 tools/run_course_inject.py --tree . --script support/lab2-long-storm.txt --log labs/lab3/evidence/lab2-long-storm.txt
```

逐条解释：

| 命令 | 证明的内容 |
|---|---|
| `make` | 内核与内嵌用户程序能够完成编译、链接 |
| `check_lab3_support.py` | 官方支撑文件一致性、头文件重复包含、跳板页地址和链接属性正确 |
| `check_lab3_vm.py` | 真正在 RISC-V 上验证降序分配、清零、回收、耗尽，以及 walk/mappages 中途失败的回滚 |
| `check_lab3_runtime.py` | 启动、页表、非法访存、保护页、跨页拷贝、fork/exec、OOM、回收和并发运行 |
| 两个 `run_course_inject.py` | 使用课程串口驱动验证 Lab2 输入和长输入风暴的回归行为 |

串口驱动的原文件保持不变。包装脚本只在内存中适配 `sh> ` 提示符和本工程无磁盘的启动参数。

### 3. 手工启动

```bash
make qemu
```

退出 QEMU：先按 `Ctrl+A`，松开，再按 `X`。不是同时按三个键。`Ctrl+C` 不等价于终止当前用户进程。

## 二、按说明书要求现场演示

建议先按这一节完成演示，再进入逐文件讲解。每次重启后 PID 和物理地址可能变化，验收重点是权限、隔离、错误返回和内核继续运行。

### 演示 1：启动、横幅与第一个用户页表

执行 `make qemu`。启动后会先看到 Lab1 横幅，再看到：

```text
DUMP-PAGETABLE begin
L2 va=0x0 pa=0x... perm=----
L1 va=0x0 pa=0x... perm=----
LEAF va=0x0 pa=0x... perm=r-xu
LEAF va=0x1000 pa=0x... perm=rw-u
LEAF va=0x4000 pa=0x... perm=rw-u
LEAF va=0x5000 pa=0x... perm=rw-u
...
LEAF va=0x3fffffe000 pa=0x... perm=rw--
LEAF va=0x3ffffff000 pa=0x... perm=r-x-
DUMP-PAGETABLE end
sh>
```

这份地址示例对应当前构建的第一个 `sh`。可以这样讲：

> 我先验证分页后系统能启动。L2 和 L1 是指向下一级页表的非叶项，所以 R/W/X 都没有设置。LEAF 是最终映射。权限字符串按 R、W、X、U 排列：代码页是 r-xu，数据页和栈页是 rw-u，陷入帧是 rw--，跳板是 r-x-。陷入帧和跳板没有 U，用户程序不能直接访问。

继续指出：

- 页表里没有 `0x2000`、`0x3000` 的叶映射，这两页是学号参数要求的保护区。
- 栈位于 `0x4000`、`0x5000`，初始栈顶与堆起点都是 `0x6000`。栈向低地址增长，堆向高地址增长。
- `0x3fffffe000` 是 TRAPFRAME，`0x3ffffff000` 是 TRAMPOLINE。
- A/D 位没有出现在四位权限字符串中；本实现建立映射时预置 A/D，避免依赖首次访问时的软件缺页处理。
- 横幅中的每字节后加点是本学号的 `LAB1_BANNER_PROTOCOL=1`，属于正确协议。页表块单独使用原始串口输出，以符合 Lab3 的行首 ABI。

如果需要现场再次打印页表，在 `sh> ` 输入：

```text
pagedump
```

> 这个程序调用本工程的观测扩展 23，内核打印当前调用进程的页表。这里打印的是 pagedump 自己的页表，所以低地址的栈和保护区位置可以和 sh 不同。dump 函数接收页表参数，没有绑定唯一全局用户页表。

### 演示 2：非法访问被隔离，父进程能够回收

在 `sh> ` 输入：

```text
badaccess
```

预期核心输出：

```text
TEST-3a PASS: wild write killed (status=-1)
TEST-3b PASS: beyond-sbrk access killed (status=-1)
sh>
```

说明：

> 第一项由子进程写地址 0。地址 0 在本实验映射为代码页，拥有 R/X/U 而没有 W，因此不能写。第二项先通过 sbrk 申请一页，再访问堆边界以外的页。硬件触发用户异常后，内核给当前进程设置非零退出状态，父进程 wait 回收，最后返回 Shell，说明异常没有破坏整个内核。

官方测试在地址 0 写入处还可能被编译器生成的其他陷阱指令终止，因此具体 `scause` 应以现场输出和反汇编为准；判定标准是代码页没有 W、非法子进程被终止、父进程得到非零状态。

### 演示 3：真实保护页、跨页拷贝与失败恢复

```text
vmtest
```

预期：

```text
CROSS-PAGE PASS
GUARD PASS
SHRINK PASS
EXEC-FAIL PASS
OOM-FORK-EXEC PASS
UNALIGNED-SBRK PASS
sh>
```

按顺序解释：

1. `sbrk(8192)` 申请两页；把字符串放在第一页末尾前 3 字节，使 `write` 的缓冲区跨页。完整输出字符串证明 copyin 能分别查询两页的物理地址。
2. 子进程从堆起点往下数 3 页写入。堆下方是两页栈，再往下一页落入保护区，因此触发 store page fault，父进程得到失败状态。
3. 负数 sbrk 收缩两页，再用 `sbrk(0)` 核对边界恢复。
4. 执行不存在的程序返回 -1，原程序继续打印，说明 exec 的失败没有销毁旧空间。
5. 逐页申请直至耗尽，再调用 fork 和 exec；两者返回 -1，原堆边界保持不变，随后仍可执行和释放原空间。
6. 用 1 字节增长再跨一页的方式检查非页对齐堆边界，最后收缩并恢复。

### 演示 4：物理配额与 OOM

```text
memcap
hi
memcap
hi
```

预期 memcap 每次都输出：

```text
TEST-4 PASS: OOM returned error after ... chunks; existing alloc intact; kernel alive
```

两次 `hi` 均能正常执行并返回 `sh> `。

> memcap 每轮扩展 64KB，直到剩余物理页不足。sbrk 必须回滚本次部分成功的分配并返回 -1，之前成功申请的内存仍可读写。再次运行 memcap 可以进一步观察退出后的资源回收，避免只验证“第一次能运行”。轮数取决于内核镜像、页表及其他进程占用，不应背固定数字。

### 演示 5：fork 物理隔离和进程回收

```text
proctest
```

预期：

```text
PROCTEST PASS: fork isolation, signed status, wait errors, exec errors, slot reuse, capacity
```

> 子进程修改自己的全局变量，父进程的变量不变，说明 fork 复制了物理页，而不是两个页表指向同一份可写数据。该程序还检查负退出状态、非法 wait 指针、重复回收和进程槽位容量。

### 演示 6：spin 与 sh 并发

建议最后演示，因为 spin 会持续输出：

```text
vmconcurrent
```

看到 `CONCURRENT shell and spin`、新的 `sh> ` 和 `spin 0` 等输出后，输入：

```text
hi
```

> vmconcurrent 的子进程 exec 为 spin，父进程 exec 为 sh。spin 忙循环期间，Shell 仍可以输入 hi 并运行。这证明两个用户空间能通过时钟中断切换。Shell 等待输入时还会在尚未消耗任何字节的前提下让出执行权，之后重试 read。

结束后用 `Ctrl+A`、`X` 退出 QEMU。本工程仍是四进程槽的教学内核，赠送 Shell 不支持 `&`、管道和命令参数，所以不要输入 `spin &`，也不要依赖尚未实现的 kill 命令。

### 演示 7：证明映射中途失败真正回滚

退出 QEMU，回到 Ubuntu：

```bash
python3 tools/check_lab3_vm.py
```

预期看到：

```text
ALLOC PASS: descending, alignment, zero, reuse, invalid/double free
ROLLBACK PASS: walk OOM, mapping page 513 OOM, empty branches reclaimed, counts conserved
PASS: isolated RISC-V allocator and page-table rollback tests
```

> 这个测试不是只检查返回值。我先把可用页消耗到只剩两页，再建立 513 页映射。前 512 页可以由同一个 L0 表覆盖，到第 513 页需要新的 L0 表时分配失败。测试检查全部新叶映射已经撤销、两个中间表也被回收，空闲页数恢复到两页。最后释放暂存页和根表，再检查总空闲页数守恒。

## 三、先讲清本次实验的整体改造

建议开场这样说：

> Lab2 已经能运行用户程序和系统调用，但使用固定的进程物理内存块，不能提供通用的动态内存管理。本次按四个阶段改造：先实现物理页分配器，再实现三级页表操作和失败回滚，然后建立完整内核页表并启用分页，最后将进程装载、fork、exec、sbrk 和用户指针访问接入页表体系。

这里应准确描述历史基线：说明书从未分页的 Lab2 介绍概念，但本工程此前为了跳板与陷入演示，已经存在一个宽泛的启动页表和固定用户页表。本次实际工作是把这些过渡实现替换为可分配、可回滚、分权限、可动态增长的实现，不能声称之前完全没有使用过 satp。

调用主线：

```text
entry.S → start.c → main.c
  → boot_vm_init → kinit → mappages → walk → kalloc
  → trap_init / uart_init / plic_init
  → proc_shell_launch → allocate_process → load_image
  → dump_pagetable → run_process → usertrapret → trampoline.userret → 用户态

用户 ecall / 异常 / 中断
  → trampoline.uservec → usertrap
  → syscall_dispatch / 用户故障退出 / 时钟切换
  → usertrapret → trampoline.userret → 用户态
```

## 四、阶段一：物理页分配器，逐文件讲解

### 文件 1：kernel/course_sid.h——先读自己的参数

定位 `LAB3_ALLOC_ORDER`、`LAB3_GUARD_PAGES`、`LAB3_MEMCAP_DELTA`。

| 参数 | 当前值 | 对实现的要求 |
|---|---:|---|
| LAB3_ALLOC_ORDER | 1 | 总是优先返回最高地址的空闲物理页 |
| LAB3_GUARD_PAGES | 2 | 用户栈下方保留两页无映射空间 |
| LAB3_MEMCAP_DELTA | 13 | 物理页分配上界从 PHYSTOP 向下扣除 13 页 |

> 这是自动派生的课程参数，我没有修改它。我在分配器和装载器中使用这些参数，而不是为了通过测试改配置。

### 文件 2：kernel/kalloc.h——先规定接口和统计口径

打开 `struct kalloc_stats`：

- `first_pa`：第一个可分配物理地址，包含在范围内。
- `limit_pa`：范围上界，不包含在范围内。
- `total_pages`：本分配器托管的物理页总数。
- `free_pages`：当前剩余空闲页数。

接口约定：`kinit()` 成功返回 0，重复初始化或非法范围返回 -1；`kalloc()` 成功返回已清零的一页，耗尽返回空指针；`kfree()` 合法释放返回 0，越界、非对齐、重复释放返回 -1。

### 文件 3：kernel/kalloc.c——按初始化、分配、回收讲

#### 第一步：位图结构

定位 `RAM_PAGES`、`BITMAP_WORDS` 和 `kmem`。

> 我用位图管理物理页，每个 bit 对应一页，1 表示空闲，0 表示已分配或不可用。128MB RAM 有 32768 页，位图占 4096 字节。位图以外还有少量范围、计数和搜索位置字段。

与说明书中的隐式空闲链表比较：

| 结构 | 分配 | 释放 | 主要取舍 |
|---|---|---|---|
| 按地址排序的空闲链表 | 取表头 O(1) | 为保持顺序插入，最坏 O(n) | 页内可存节点，但大批量回收可能退化成 O(n²) |
| 本实现位图 | 向低地址扫描位图字，再在 64 位内找最高位 | 找到 bit 为 O(1) | 额外约 4KB 元数据，批量回收更稳定 |

这里 O(1) 指释放的位图维护；清理一页还会固定写入 4096 字节。不要把位图分配说成绝对 O(1)，它可能扫描多个位图字。

#### 第二步：kinit

依次指出以下语句：

```c
uint64 limit = PHYSTOP - (uint64)LAB3_MEMCAP_DELTA * PGSIZE;
uint64 first = PGROUNDUP((uint64)kernel_end);
```

> `kernel_end` 是链接脚本导出的镜像末尾。我向上对齐，避免分配到内核最后一个不足整页的部分；上界扣除 13 页，然后把这个半开区间对应的 bit 标记为空闲。最后初始化总页数、空闲页数和最高候选位图字。

接着指出 `initialized` 检查：重复初始化不能把已经分配出去的物理页重新标记为空闲。

#### 第三步：kalloc

按以下顺序讲：

1. 未初始化或空闲页为 0，直接返回空指针。
2. 从 `search_word` 向下跳过全零位图字。
3. 在选定字里从 bit 63 向下找最高空闲位。
4. 将 bit 清零并减少空闲计数。
5. 根据页号计算 `KERNBASE + 页号 * PGSIZE`。
6. 清零整页再返回。

> 清零既满足新页表初始无映射的要求，也防止上一个进程留下的数据被下一个进程读取。

#### 第四步：kfree

先检查初始化状态、4KB 对齐、托管区间和位图状态。确认合法后填充 `0xA5`，再将 bit 置 1 并增加空闲页计数。如果释放的是更高地址的页，还要上移 `search_word`。

> 更新 search_word 是为了保证释放后的高地址页仍优先被重新分配。填充垃圾数据便于发现释放后继续使用的悬挂指针；它不能代替页表权限或引用生命周期管理。

本实验只在单核运行；分配路径没有跨核自旋锁。正常内存管理运行在不进行内核抢占的路径，UART 和内核时钟中断不会操作分配器。不能把它描述为已支持多核并发的分配器。

## 五、阶段二：三级页表与回滚，逐文件讲解

### 文件 4：kernel/riscv.h——使用体系结构定义

这是官方支撑文件。本次保留增量包的 include guard 修复，主要使用已有宏和 CSR 封装。

依次定位：

- `PGSIZE`：4096。
- `pte_t`：64 位页表项；`pagetable_t`：指向 512 个页表项的指针。
- `PXSHIFT`、`PX`：从 VA 中提取三级各自的 9 位索引。
- `PTE_V/R/W/X/U`：有效性与访问权限。
- `PA2PTE`、`PTE2PA`：物理地址与 PPN 字段之间的编码转换。
- `MAKE_SATP`：MODE=8 与根页表物理页号组合。
- `sfence_vma`：刷新本 hart 的地址翻译缓存。

> SV39 的低 39 位由三级各 9 位的索引和 12 位页内偏移组成。本课程 MAXVA 进一步只使用低半规范地址空间，避免高位符号扩展，因此实际使用的上限是 2³⁸，而不是把所有 39 位数值都当成合法低地址。

`R/W/X=0` 且 V=1 才表示指向下一级页表；只看 V 不能判断它是数据页。

### 文件 5：kernel/vm.h——统一页表接口

接口包括 `walk`、`mappages`、`uvmunmap`、`vmfree`、`dump_pagetable`。已有的 `SBRK_EAGER` 和 `SBRK_LAZY` 常量保留；本实验统一执行 EAGER 语义，没有实现缺页时按需申请的 LAZY 机制。

### 文件 6：kernel/vm.c——最重要的答辩文件

#### 第一步：walk

定位 `walk(pagetable_t table, uint64 va, int alloc)`。

> walk 先检查虚拟地址上界，再从 level 2 走到 level 1。如果已有有效非叶项，就取出下一级表的物理地址。如果不存在且允许分配，就调用 kalloc 创建一个清零的页表页，并写入只有 V 的非叶项。走到 level 0 后，返回叶 PTE 的地址。

为什么返回 PTE 指针：调用方要修改映射和权限，只有返回物理地址无法修改原页表项。

指出 `created[2]` 和 `fail:`：

> walk 最多新建两页中间表。我记录本次新建的父链接。后续分配失败时，从最深层开始清父链接并释放页表页，不能把此前就存在的正常表释放掉。

`alloc=0` 用于查询；不存在就失败，不能因为一次检查偷偷分配物理内存。

#### 第二步：mappages

先讲入口检查：size 不为零，VA/PA 对齐，范围不越过 MAXVA，权限合法；W 必须配合 R。

再讲循环：每次调用 walk 取得叶项，确认没有已有有效映射，填入 PA 与权限，推进一页。

> 重复映射返回 -1，不覆盖原映射。这样调用错误不会悄悄改变已有物理页归属，也不必让整个内核 panic。

最后重点讲失败分支：

```c
uvmunmap(root, va, (cursor-va)/PGSIZE, 0);
return -1;
```

> cursor 指向失败页，所以这里只撤销本次已经成功建立的前缀，不碰失败页已有映射。最后一个参数为 0，表示不释放调用方传进来的物理数据页；这些物理页不是 mappages 分配的，释放责任属于调用方。

可以直接口述资源不变式：

> mappages 负责自己建立的映射和中间页表；调用方负责传入的数据物理页。失败时，新映射不能残留，新中间表不能泄漏，原有有效映射不能被覆盖。每个数据页只能被它的所有者释放一次。

#### 第三步：uvmunmap 和 prune

定位 `uvmunmap`：查询叶项，取出 PA，先将 PTE 置零，执行刷新，再根据 `release` 决定是否 kfree 数据页。

> 先使映射无效并刷新，再释放数据页，可以避免旧映射继续访问已经重新分配给别人的物理页。

定位 `prune`：记录根到叶的两级链接，先检查 L0 是否全空；为空则清父链接并释放；再检查 L1 是否全空；不空立即停止。根表在普通拆映射时保留。

> prune 不会只因为某个区间拆完，就把同一页表中的其他有效映射一起释放。

#### 第四步：vmfree

递归遍历有效项。非叶项递归释放下级表；叶项仅在 `payload=1` 且设置了 PTE_U 时释放背后的物理页，最后释放当前表页。

> 这样用户代码、数据、栈、堆会被回收；没有 U 的跳板共享页不会被当作进程私有页释放，trapframe 则由进程资源释放函数单独回收。调用方必须保证正在销毁的表不再作为活动 satp 使用。

#### 第五步：dump_pagetable / dump_level

按索引升序递归，并通过 `base | (index << PXSHIFT(level))` 算出每项覆盖的虚拟起始地址。分别输出 L2、L1 和 LEAF，权限固定四个字符。

> A/D 不混入 perm，非叶必须是四个横线。开始和结束标记遵循赠送 ABI。

### 文件 7：kernel/vm_printf.c——为什么额外有这个小文件

通过宏把现有格式化器实例化为 `vmprintf`，输出函数改为 `uartputc_sync`。它复用相同的格式化实现，但直接输出字符，避免 Lab1 的每字节加点协议污染页表 ABI。没有修改官方串口协议参数。

## 六、阶段三：内核页表和启动，逐文件讲解

### 文件 8：kernel/boot_vm.c——构建内核映射

先看顶部：根表、高地址 L1/L0 表和启动 trapframe 都按页对齐，静态存放在内核镜像里。其他映射需要的中间表由分配器创建。

定位 `boot_vm_init`，按顺序讲：

1. 检查跳板物理地址页对齐。
2. 调用 kinit，之后才允许 walk 动态分配页表页。
3. 映射 UART0 一页，RW、无 U。
4. 映射 PLIC 区域 4MB，覆盖当前中断驱动直接访问的寄存器，RW、无 U。
5. 将 `[KERNBASE, PHYSTOP)` 全部恒等映射为 RWX、无 U。
6. 高地址映射 TRAMPOLINE 为 RX，TRAPFRAME 为 RW。
7. 刷新 TLB，写 satp，再刷新。
8. 读写高低别名做启动自检。

为什么要映射到 PHYSTOP：

> kalloc 返回的物理页、用户数据页和后续页表页在内核镜像之外，内核还要直接访问它们的物理地址。如果只映射到 kernel_end，分页后第一次访问这些页就会缺页。

为什么配额扣除了 13 页，内核仍映射到 PHYSTOP：

> 配额控制的是哪些页可以被分配，恒等映射决定哪些物理地址在内核中可访问，两者不是同一个概念。被配额排除的页不会进入分配器。

为什么内核 RAM 暂时 RWX：

> 按本阶段说明书的约束，预置链接脚本没有提供 etext 分界，内核统一 RWX 是课程允许的过渡方案。用户代码页仍严格去掉 W；不能用内核的过渡策略放宽用户代码权限。

为什么不映射 CLINT：

> 这里的时钟通过 rdtime/stimecmp CSR 配置和重置，不直接读写 CLINT 的 MMIO 地址，所以不需要 CLINT 恒等映射。UART 和 PLIC 的驱动确实直接访存，因此必须映射。

`boot_trapframe_select`：运行哪个进程，就把内核高地址 TRAPFRAME 别名更新为那个进程的实际 trapframe 物理页，再执行 sfence.vma。这让内核中的陷入处理代码使用统一虚拟地址。

### 文件 9：kernel/entry.S、kernel/start.c、kernel/main.c——按启动链讲

`entry.S` 是已有引导代码：禁中断、准备启动栈、非零 hart 停驻、进入 start。

`start.c`：设置 MPP=S、mepc=main、初始 satp=0，委托异常和中断，配置 PMP。为本次并发验证启用 Sstc 与计数器访问，并将比较寄存器先设为很大值。

`main.c`：先建立内核页表，再初始化异常入口、UART 和 PLIC；设置下一次时钟比较值并开启 SEIE/STIE；打印原 Lab1 横幅，最后启动 Shell。

> 当前 QEMU virt 的时钟频率下，比较值增量 100000 对应约 10ms。这里提供最小的用户态轮转用于 Lab3 并发验收，后续 Lab4 的指定调度策略尚未实现。

### 文件 10：kernel/memlayout.h、kernel/kernel.ld——布局依据

这两份课程支撑文件保持当前基线。展示 KERNBASE、PHYSTOP、TRAMPOLINE、TRAPFRAME、KSTACK 宏和链接脚本的 `kernel_end`。

> 我没有采用 KSTACK(p) 高地址内核栈映射，进程内核栈直接使用分配器提供的一页物理内存，在内核恒等映射下访问。因此本实现没有高地址内核栈保护页。与 Lab0 图纸对照时，应把“高地址 KSTACK”标为未采用，把实际内核栈画在 RAM 恒等映射区域；用户栈下方的两页保护区仍然存在。

## 七、阶段四：独立用户空间，逐文件讲解

### 文件 11：Makefile、Makefile.upgrade——先说明构建改造

打开 Makefile 的 `OBJS`：增加 `kalloc.o`、`vm.o`、`vm_printf.o`，把新功能真正链接进内核。

打开 `UPROGS` 的追加部分：加入 `badaccess memcap vmtest vmconcurrent pagedump`。官方 badaccess/memcap 测试源文件从 support 复制到 user 后参与已有内嵌构建。

定位 `user-flat/user-lab3.ld`：从不可修改的 `user/user.ld` 生成派生脚本，在 `.data` 前插入页对齐和 `data_start` 符号。原始脚本仍按地址 0 链接。

> 如果代码和可写数据挤在同一页，就不能同时让代码不可写又允许修改数据。我在构建期把数据起点推到下一页，从源头提供页粒度权限边界。

官方 `Makefile.upgrade` 规则保持不变。针对用户二进制的目标变量，把 LD 定向到链接包装器，内核仍使用普通的 RISC-V 链接器。

### 文件 12：tools/link_user.py、tools/gen_user_meta.py

`link_user.py` 只替换用户链接命令中的脚本路径，随后调用真实 `riscv64-unknown-elf-ld`，保留其他参数。

`gen_user_meta.py` 从每个 ELF 读取入口，并通过 nm 获取 `end`、`data_start`，生成 `kernel/user_meta.h`。

> flat binary 不携带 ELF 段权限。我保留赠送的二进制表 ABI，额外生成按名称匹配的元数据表，把 entry、内存长度和数据起点传给内核。内核装载时才据此决定 RX 或 RW。这里使用 ELF 符号提取等价边界信息，没有硬编码每个程序的大小。

`kernel/user_meta.h` 和 `kernel/userimg.S` 是生成文件，不手工编辑。后者存储程序起止地址、名称和内嵌镜像，find_image 按表匹配。

### 文件 13：kernel/proc.h——进程结构演进

对照 `struct proc`：

| 字段 | 用途与生命周期 |
|---|---|
| pagetable | 进程独立根表；创建时建立，exec 成功时替换，回收时销毁 |
| sz | 当前堆边界；sbrk 成功后更新 |
| heap_base | 堆最低边界，防止负 sbrk 破坏栈和镜像 |
| guard | 保护区起点，用于布局说明 |
| kernel_stack | 私有内核栈顶，由 kalloc 分配一页，回收时减一页取得基址 |
| frame | 独立 trapframe 物理页 |
| image_size | 用户镜像内存长度 |
| parent_pid / wait_address | wait 与退出状态交付 |

> 取消了固定物理 bank 的基地址依赖。相同用户 VA 在不同进程里可以指向不同 PA，布局不再依赖把镜像拷贝到一整块固定槽位。

### 文件 14：kernel/proc.c——按进程生命周期讲

#### 第一步：new_table 和 allocate_process

`allocate_process` 找空闲进程槽，分配独立的 trapframe、内核栈和根表。任何一步失败调用 release_process 清理已获得的资源。

`new_table` 创建根表，并映射：共享跳板 RX、私有 trapframe RW，两者都没有 PTE_U。

> trapframe 是每个进程独立的；trampoline 的代码物理页是所有进程共享的。共享跳板没有 U，不等于它在用户页表中不存在，它是在 supervisor 陷入和返回路径使用的。

#### 第二步：load_image——权限、保护区和 exec 原子替换

按源码顺序讲：

1. find_image 找镜像和边界元数据。
2. 用 new_table 构造候选页表，不修改原页表。
3. 镜像长度向上页对齐得到 guard 起点。
4. 跳过两页保护区，不为它们分配物理页。
5. 数据边界前映射 RXU，数据、栈等映射 RWU。
6. 通过物理页地址把二进制内容复制到对应页；BSS 由 kalloc 的清零保证。
7. 全部成功后，才更新 pagetable、sz、heap_base、guard 和用户寄存器。
8. 最后销毁旧页表。

> exec 失败时，只销毁候选表，原 pagetable、堆边界和用户寄存器保持可继续执行的状态。候选页表建立成功之前，绝不能先释放旧空间。

说明 `add_page` 的释放职责：先申请数据页，再调用 mappages；如果映射失败，由 add_page 回收数据页，而 mappages 负责新中间表。这与阶段二的资源不变式一致。

#### 第三步：proc_sbrk

`old=sz` 保存旧堆边界，返回值总是旧边界，失败则是 -1。

正数增长：从 `PGROUNDUP(old)` 开始逐页即时分配，直到覆盖新的边界。中途失败，拆除本次成功的新页并回收，sz 不更新。

负数收缩：先确保不会小于 heap_base，再释放从 `PGROUNDUP(next)` 到 `PGROUNDUP(old)` 之间的整页。仍承载有效字节的尾页保留。

参数 0：不分配，不释放，返回当前边界。

> sz 是字节级逻辑边界，映射是页级。小幅增长不一定新增物理页，小幅收缩也不一定释放页。对于已经映射的最后半页，硬件无法单独限制到每个字节，这与页粒度 EAGER 管理一致。

#### 第四步：proc_fork

创建子进程基础资源，再遍历父空间 `[0, sz)`：

- 没有有效 PTE 的位置跳过，所以保护区空洞能保留。
- 有效用户页重新分配物理页，按父权限建立子映射，再复制 4096 字节。
- 最后复制用户寄存器，将子 a0 设为 0，父调用返回子 PID。
- 任一步失败释放整个尚未运行的子进程。

> trapframe 和 trampoline 位于高地址，不在这个低地址遍历区间中。子 trapframe 在 allocate_process 已单独创建，里面的用户寄存器内容随后复制；跳板继续共享同一代码页。

#### 第五步：proc_wait、proc_exit、release_process

wait 先检查用户状态指针是否可写，发现已退出子进程则 copyout 状态并回收；有可运行子进程则父进程进入 WAITING 并切换。

exit 把自己标记 EXITED。如果父进程正在 wait，就把退出状态安全写给父进程，设置父进程返回值，切回父进程。

指出 `deferred` 与 `proc_reap_deferred`：

> 子进程正在自己的内核栈里执行 exit，不能当场 kfree 当前栈。我先把这个进程登记为延后回收，切换到其他进程；等另一个进程下一次进入 usertrap，已经在另一个内核栈上，才真正释放旧子进程的页表、trapframe 和内核栈。

这是防止“释放自己还在使用的内核栈”的关键，不应省略。

#### 第六步：run_process、proc_yield

run_process 禁中断、更新 current 和状态，调用 boot_trapframe_select 切换内核 TRAPFRAME 别名，然后进入 usertrapret。

proc_yield 从当前槽的下一个位置寻找 RUNNABLE 进程；只有存在下一进程才切换。时钟中断可以切换保存完整用户现场的任务；read 无数据时可以通过退回 epc 4 字节，在下一次运行时重新执行 ecall。

> 这不是通用的内核栈上下文切换器：只有用户现场保存完整，或 read 尚未消费任何数据、能够安全重试时，才丢弃当前 C 调用链。后续复杂阻塞系统调用需要 Lab4 的完整调度和睡眠机制。

### 文件 15：kernel/user_mem.c、kernel/user_mem.h——安全搬运用户数据

这些接口在 Lab2 已有基础，本次继续复用，接入动态页表；不能把整个文件都说成这次新写。

先看 `user_page_pa`：逐级查询，要求 V；仅接受 4KB 叶页；验证物理地址位于 RAM；要求 U/R，写入还要求 W。

再看 `user_accessible`：检查地址加长度不溢出，按页验证整个区间。

最后看 `user_copyin` 和 `user_copyout`：先校验全区间，再按页计算：

```text
页内偏移 = VA & 4095
本轮长度 = min(剩余长度, 4096 - 页内偏移)
物理访问地址 = 当前叶项的 PA + 页内偏移
```

> 相邻虚拟页未必对应相邻物理页，所以跨页后必须重新查页表，不能只翻译第一个地址然后连续 memcpy。整个区间预检查还能避免 copyout 写了一半才发现后半段非法。本实现按页查询后用字节循环搬运，减少逐字节 walk 的开销，同时不依赖跨页物理连续性。

说明书称 copyin/copyout，本工程函数名为 user_copyin/user_copyout，满足相同语义。

### 文件 16：kernel/syscall.c——用户指针审查结果

定位 `syscall_dispatch` 的 `SYS_sbrk`：调用号仍为官方的 12，按 32 位有符号 int 解释 n，并转交 proc_sbrk。

定位 `SYS_dump_pagetable`：私有观测扩展为 23，定义在 `vm_debug.h`，未修改官方 syscall.h；只打印 myproc 的页表，没有开放任意内核指针。

依次解释需要处理用户指针的位置：

| 调用点 | 处理方式 |
|---|---|
| sys_write 的用户缓冲区 | user_readable 检查，user_copyin 搬到 64 字节内核缓冲区，再写串口 |
| sys_read 的目标缓冲区 | console_read 预检查后使用 user_copyout |
| proc_exec 的程序名 | user_copyin 逐字节读取，有长度上限和字符串终止检查 |
| proc_wait 的状态指针 | user_writable 预检查，user_copyout 交付状态 |

exec 的 argv 在当前教学阶段未装载，代码没有直接解引用这个用户指针；不要声称已实现完整参数栈。getpid、exit、sbrk 都使用整数参数，不需要把整数当作用户地址处理。

> 内核加载内嵌镜像时读取的是内核自己的镜像地址，写的是已经通过页表查到的物理页；这类已知内核地址的拷贝不同于直接信任用户传入的 VA。

### 文件 17：kernel/trapframe.h、kernel/trampoline.S、kernel/trampoline_link.S

trapframe.h 定义与赠送汇编一致的偏移，并用静态断言检查。如 kernel_satp 在 0，kernel_sp 在 8，epc 在 24，a0 在 112。

> C 和汇编必须遵守同一个布局，否则保存的用户寄存器会被当成另一个字段。该 ABI 检查是以前已有的基础。

trampoline.S 使用官方 v2 修复版：段带 `ax` 属性，并按 4KB 对齐。跳板在内核页表与每个用户页表里使用同一个高地址 VA，并指向同一物理页。

`uservec` 顺序：保存寄存器 → 读取内核栈和内核 satp → 切换内核页表并刷新 → 调用 usertrap。

`userret` 顺序：刷新指令缓存 → 刷新/切换用户 satp/再刷新 → 从 TRAPFRAME 恢复寄存器 → sret。

> 切用户页表必须在跳板里做。如果在普通内核 C 函数里写用户 satp 后继续执行，下一条内核指令的 VA 就可能已经没有映射。跳板在切换前后同址可执行，才能保证取指连续。

trampoline_link.S 是链接包装入口；Makefile 中补了对 trampoline.S 的依赖，保证赠送汇编改动后包装目标会重编译。

### 文件 18：kernel/trap.c——异常隔离与返回

先看 usertrap 第一条操作：把 stvec 改为内核异常入口，然后回收延后销毁的进程。

> 官方 uservec 不会替我切 stvec。如果漏掉，进入内核后的下一次异常还可能跳回用户入口，现场解释会错，甚至覆盖 trapframe。

再看 handle_user_trap：保存 sepc；ecall 把 epc 加 4 后分发系统调用；外部中断交给 PLIC/UART；时钟中断重新设置 stimecmp 并轮转；其他用户故障输出诊断并 proc_exit(-1)。用户保护页读写通常对应 scause 13/15，取指缺页对应 12。

kerneltrap 与用户故障区别：内核异常说明内核自身出了问题，不能冒充普通用户退出；外设和时钟中断则完成处理后恢复原来的 sepc/sstatus。

最后看 prepare_return 和 usertrapret：禁中断，填内核 satp/栈/入口，stvec 指向高地址 uservec，清 SPP、置 SPIE，设置 sepc，再通过高地址间接调用跳板 userret。

> 返回时从当前进程的 pagetable 重新计算 satp，不能在 exec 换表后仍使用旧值。切换进程时也必须匹配新的 frame、内核栈和页表。

### 文件 19：kernel/console.c、kernel/plic.c——回归和并发相关

PLIC 和 UART 中断驱动主要沿用 Lab2。console_read 仍然先检查整个目标缓冲区；有数据则通过 copyout 写用户页；没有消费任何字节而又存在其他可运行任务时，调用 proc_yield(1) 让出执行权。

> 必须在 done=0 时才能重新执行 read，否则已经消费的字节会因系统调用重试而丢失。已有输入后直接返回已读取长度，保持字符流短读语义。

## 八、测试文件逐个讲什么

| 文件 | 对照源码要讲的行为 |
|---|---|
| user/badaccess.c / support/tests/badaccess.c | 官方测试，两次 fork，分别非法写代码和越过 sbrk 分配区，wait 检查非零状态 |
| user/memcap.c / support/tests/memcap.c | 官方测试，64KB 一轮扩展，失败后检查之前的内存仍有效 |
| user/vmtest.c | 两页跨页 write、真实保护区、负 sbrk、exec 不存在、资源耗尽时 fork/exec、非对齐边界 |
| user/proctest.c | 复用此前进程测试，检查深拷贝、状态码和槽复用 |
| user/pagedump.c | 用寄存器传递观测系统调用号，触发当前进程页表打印 |
| user/vmconcurrent.c | fork 后子 exec spin、父 exec sh，直观验证独立空间轮转 |
| tools/check_lab3_vm.py | 用独立小内核进行物理页耗尽、walk 单级回滚、mappages 第 513 页失败回滚验证，不替换正式镜像 |
| tools/check_lab3_runtime.py | 自动发送用户命令并匹配每一步的输出，保存真实串口记录 |
| tools/check_lab3_support.py | 核对支撑文件、跳板链接和重复包含，防止仅源码看起来正确 |

`user/user.ld`、`user/usys.pl`、`Makefile.upgrade`、官方测试原件和课程串口驱动保留。不要在答辩时把赠送件当成自己从零实现的功能。

## 九、说明书五项设计决策，可以直接回答

### 1. 映射失败由谁释放什么

> mappages 清理本次成功的叶项和空中间表，不释放传入 PA。walk 自己分配的未完成表页自己撤销。add_page 负责释放自己新申请但未映射成功的数据页。sbrk 再负责回收整个增长请求中已经成功的前缀。exec/fork 失败销毁候选空间。这样资源释放逐层对应，不泄漏也不双重释放。

### 2. guard 是否分配物理页

> 不分配。装载时直接跳过学号要求的两页，fork 遍历时同样跳过无效项。用户访问时硬件报缺页，usertrap 把它当作当前用户进程故障并退出，内核继续运行。

### 3. 配额如何传播错误

> 上界是 PHYSTOP 减 13 页，起点是 kernel_end 向上对齐。kalloc 耗尽返回 0；walk 返回 0；mappages/add_page/load_image 返回 -1；sbrk/fork/exec 向用户返回 -1，并在每一层撤销本层创建的资源。

### 4. 为什么按页拷贝

> 逐字节查页表太慢，直接 memcpy 用户 VA 不安全。我先验证全区间，再按页查物理页并拷贝页内连续部分。这样既能处理物理不连续的跨页缓冲区，也能拒绝缺失 U 或缺失写权限的页。

### 5. proc 字段如何维护

> allocate_process 建 frame、栈和基础表；load_image 建镜像并设置 sz、heap_base、guard；fork 深拷贝；exec 候选表全部成功才替换；run_process 选择别名和当前表；wait/延后回收路径最终调用 release_process 销毁。

## 十、三道思考题与常见追问

**TLB 未命中需要几次内存访问？**

> 对普通 4KB、无缓存命中的完整三级遍历，先读三级 PTE，需要三次页表内存访问；再加最终数据访问，一次 load 总计可达四次。TLB、页表遍历缓存和普通缓存能降低开销；大页可减少遍历层数。本实现用户页使用 4KB。

**为什么先撤映射再释放页？**

> 如果先释放，分配器可能把同一物理页交给另一个进程，而旧 PTE 或 TLB 还让旧进程访问它，造成跨进程读写。要先清 PTE、刷新，再释放。多核时还需要向其他使用该地址空间的 hart 发起 TLB shootdown，单个 sfence.vma 不会替其他 hart 刷新。

**copyin 与 memcpy 有什么不同？**

> memcpy 信任地址在当前地址空间可直接访问，不验证用户权限。copyin 把输入当作不可信的用户 VA，查询指定进程页表并检查 U/R，再通过内核可访问的物理映射读取。copyout 还要求 W，否则用户可以借内核写代码页或其他禁止写的位置。

**为什么用户页表里有陷入帧，但用户不能读？**

> 页表存在映射不意味着 U 态可访问。TRAPFRAME 的 U 位没有设置，uservec 进入 supervisor 后才能使用这张用户页表里的 supervisor 映射。

**为什么 fork 不复制一个连续物理块？**

> 动态分配后每个虚拟页的 PA 可以不连续，中间还有 guard 空洞。必须按 PTE 找到每个实际页再复制，才能保持权限和空洞。

**没有刷新 TLB 会怎样？**

> 页表内存已经更新，处理器却可能仍使用旧的 PA 或旧权限，出现访问已释放页、权限修改不生效或切换后读错数据。建立/拆除映射、更新 trapframe 别名和切换 satp 都要考虑刷新。

## 十一、最后用一分钟串起完整流程

> 我先从学号参数确定降序分配、13 页配额和两页保护区。kinit 根据 kernel_end 和 PHYSTOP 建位图，kalloc 返回清零的物理页，kfree 做合法性检查和回收。
>
> 然后我实现 walk、mappages 和拆映射。walk 创建缺失的中间表，mappages 写叶项；出现 OOM 时，叶映射、中间表和数据页按明确的所有权逐层撤销。
>
> 接着建立完整内核恒等映射和高地址跳板映射，写 satp 启用分页，保留 UART、PLIC 和全部 RAM 的可访问性。
>
> 最后把用户程序按 0 地址装载，通过构建期数据边界把代码设为 RX、数据设为 RW，跳过保护区，建立私有栈、frame 和堆。系统调用通过受控拷贝访问用户数据，sbrk 进行即时分配和失败回滚，fork 逐页深拷贝，exec 候选空间成功后才替换。跳板保证切页表时连续执行，用户故障只终止当前进程。
>
> 我用官方 badaccess/memcap、跨页和保护页自测、强制中途 OOM 的内核测试、串口回归以及 spin/sh 并发验证这些行为。

## 十二、现场时间有限时的打开文件顺序

按这个顺序打开即可，不必把所有赠送件逐行念一遍：

1. `kernel/course_sid.h`：解释三个参数。
2. `kernel/kalloc.c`：kinit → kalloc → kfree。
3. `kernel/riscv.h`：PX、PTE、MAKE_SATP。
4. `kernel/vm.c`：walk → mappages → uvmunmap/prune → dump。
5. `kernel/boot_vm.c`：内核映射清单、satp、TLB。
6. `Makefile`、`tools/gen_user_meta.py`：为什么代码和数据能分权限。
7. `kernel/proc.h`、`kernel/proc.c`：装载 → sbrk → fork → exec → 回收。
8. `kernel/user_mem.c`、`kernel/syscall.c`：跨页和用户指针审查。
9. `kernel/trap.c`、`kernel/trampoline.S`：陷入、故障退出和返回。
10. `user/vmtest.c`、`tools/check_lab3_vm.py`：用测试证明关键边界，而不是只口述正确。

正式串口证据位于 `labs/lab3/evidence/`。讲解时优先展示本机现跑结果，归档记录作为补充。
