# ospractice — 操作系统实践

学号 2024302111309 的操作系统实践代码仓库。全学期在这一棵代码树上累积演进。

## 目录结构

```
Makefile              课程提供的构建入口(qemu/clean 目标不可改)
kernel/               内核源码树
  course_sid.h        个性化参数(自动生成,勿改)
  kernel.ld           链接脚本(预置)
  riscv.h             底层硬件宏(预置)
  memlayout.h types.h 预置头文件
  entry.S start.c console.c printf.c main.c   ← 需要自己实现的五个文件
docs/                 课程文档
  我的参数.txt         15 项个性化参数速查
  基线包README.txt     基线包原始说明
  lab0/               热身实验说明书、学生须知、环境安装指引、无gdb调试手册、xv6 book
  lab1/               lab1 实验说明书
labs/                 各轮实验的交付物(图纸、设计笔记、自写测试)
  lab0/               控制流图、数据结构快照、时钟中断时序图
tools/                课程工具
  preflight.py        环境自检
  check_expect.py     expect_banner.txt 格式自检
  monpeek.py          QEMU Monitor 脚本式读取
env/                  环境搭建与验证脚本 + 验证报告存档
```

## 环境

WSL2 Ubuntu,工具链装在 WSL 内。已通过 `preflight.py` 自检,详见 [env/环境验证报告.txt](env/环境验证报告.txt)。

| 组件 | 状态 |
|---|---|
| riscv64-unknown-elf-gcc / ld / objdump / readelf / addr2line | 可用 |
| qemu-system-riscv64 | 可用,`-machine virt` + `-smp 2` 均可实例化 |
| git / python3 / perl / make | 可用 |
| riscv64-unknown-elf-gdb | 不可用 — 按课程设计,用 `-d int` / `-d in_asm` / QEMU Monitor 替代 |

## 常用命令

在 WSL 内进入本仓库目录后:

```bash
make                 # 构建 kernel/kernel
make qemu            # 启动(退出:Ctrl-a 然后 x)
make clean

python3 tools/preflight.py                          # 环境自检
python3 tools/check_expect.py 2024302111309         # 校验 expect_banner.txt
```

调试三板斧(详见 [docs/lab0/无gdb调试手册.txt](docs/lab0/无gdb调试手册.txt)):

```bash
# 异常/中断日志 —— 黑屏第一手段,async:0 才是异常
qemu-system-riscv64 -machine virt -bios none -kernel kernel/kernel -nographic -d int -D int.log &
QPID=$!; sleep 3; kill $QPID
grep 'async:0' int.log | head -3

# 指令追踪 + 地址回源码
qemu-system-riscv64 -machine virt -bios none -kernel kernel/kernel -nographic -d in_asm -D trace.log &
riscv64-unknown-elf-objdump -d kernel/kernel > kernel.asm
riscv64-unknown-elf-addr2line -e kernel/kernel 0x80000123
```

## 我的个性化参数

lab1 相关:`LAB1_BANNER_PROTOCOL = 1`(每字节后加 `.`)、`LAB1_STACK_KB = 8`。
banner 需含学号十进制 `2024302111309` 与 `2024302111309 % 97` 的十六进制(小写、无前导零)。
全部 15 项见 [docs/我的参数.txt](docs/我的参数.txt)。

## Git 工作流

```bash
git tag labN-start                 # 合并增量包后
git add -A && git commit -m "..."  # 随做随提交,bisect 靠它
git tag labN-submit                # 验收前锁定
git archive --format=zip -o 提交-labN-2024302111309.zip labN-submit
```

## 当前进度

- [x] lab0 环境搭建与自检通过
- [ ] lab0 三份图纸(控制流图 / 数据结构快照 / 时钟中断时序图)→ `labs/lab0/`
- [x] lab1 内核启动、打印与 Banner 验收通过
- [x] lab2 陷入、系统调用、中断控制台、Shell 装载和内嵌命令通过

## Lab2 学习与验收入口

- [详细学习文档](labs/lab2/逐步实现与讲解.md)：阶段四集中在第17步，含概念解释、地址和父子进程例子。
- [PDF要求对照](labs/lab2/PDF验收对照.md)、[验收记录](labs/lab2/验收记录.md)、[设计笔记](labs/lab2/设计笔记.md)。
- [现场运行与问答](labs/lab2/现场运行与问答.md)：运行hi/badecall/proctest，最后用spin演示输入中断。

正式 `make qemu` 启动到 `sh> `。spin无限运行，退出QEMU按Ctrl+a后按x。

```bash
python3 tools/run_lab2_checks.py --clean  # 源码清理重建及14项验收
```

原赠送串口脚本通过 `tools/run_course_inject.py` 适配sh提示符和无磁盘启动；赠送文件未改。当前使用四个固定进程槽和wait驱动的协作执行，read为空时允许中断忙等；详细能力范围及RWX程序页的限制见学习文档17.16。
