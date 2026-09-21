"""Regenerate the five Lab0 SVG diagrams from the verified xv6 walkthrough."""

from html import escape
from pathlib import Path


OUT = Path(__file__).parent / "figs"
FONT = "Microsoft YaHei, Noto Sans CJK SC, sans-serif"


class Drawing:
    def __init__(self, width, height, title, subtitle):
        self.width = width
        self.height = height
        self.parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}">',
            '<defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto">'
            '<path d="M1 1 L9 5 L1 9 Z" fill="#66788A"/></marker></defs>',
            f'<rect width="{width}" height="{height}" fill="#F7F9FA"/>',
            f'<rect width="{width}" height="78" fill="#153B45"/>',
        ]
        self.text(36, 36, title, 23, "#FFFFFF", "bold")
        self.text(36, 63, subtitle, 14, "#D9ECEB")

    def rect(self, x, y, width, height, fill="#FFFFFF", stroke="#C9D7D9", radius=5):
        self.parts.append(
            f'<rect x="{x}" y="{y}" width="{width}" height="{height}" '
            f'rx="{radius}" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>'
        )

    def text(self, x, y, value, size=16, fill="#18313B", weight="normal", anchor="start"):
        self.parts.append(
            f'<text x="{x}" y="{y}" fill="{fill}" font-family="{FONT}" '
            f'font-size="{size}" font-weight="{weight}" text-anchor="{anchor}">{escape(str(value))}</text>'
        )

    def line(self, x1, y1, x2, y2, arrow=False, color="#66788A", width=2):
        marker = ' marker-end="url(#arrow)"' if arrow else ""
        self.parts.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
            f'stroke="{color}" stroke-width="{width}"{marker}/>'
        )

    def box(self, x, y, width, height, title, lines, accent="#087E83", fill="#FFFFFF"):
        self.rect(x, y, width, height, fill=fill)
        self.rect(x, y, 5, height, fill=accent, stroke=accent, radius=0)
        self.text(x + 19, y + 29, title, 17, "#18313B", "bold")
        for index, item in enumerate(lines):
            self.text(x + 19, y + 55 + index * 22, item, 14, "#405761")

    def note(self, x, y, width, title, lines):
        height = 48 + 23 * len(lines)
        self.rect(x, y, width, height, fill="#FFF8E9", stroke="#DFC57A")
        self.text(x + 16, y + 29, title, 16, "#745413", "bold")
        for index, item in enumerate(lines):
            self.text(x + 16, y + 53 + index * 23, item, 14, "#5B5140")

    def save(self, name):
        OUT.mkdir(exist_ok=True)
        with (OUT / name).open("w", encoding="utf-8", newline="\n") as file:
            file.write("\n".join(self.parts + ["</svg>", ""]))


def timeline(name, title, subtitle, rows, notes):
    row_gap = 101
    first_y = 103
    notes_y = first_y + len(rows) * row_gap + 10
    drawing = Drawing(1320, notes_y + 47 + 23 * len(notes) + 35, title, subtitle)
    for index, (stage, heading, detail, context, accent) in enumerate(rows):
        y = first_y + index * row_gap
        drawing.box(35, y, 180, 87, stage, [], accent)
        drawing.box(232, y, 740, 87, heading, detail, accent)
        drawing.box(989, y, 296, 87, "运行状态", context, accent, "#F2F6F6")
        if index + 1 < len(rows):
            drawing.line(224, y + 88, 224, y + 100, arrow=True)
    drawing.note(35, notes_y, 1250, "验收批注：为什么这样画", notes)
    drawing.save(name)


timeline(
    "图1-材料一-全系统控制流图.svg",
    "材料一｜echo hi 的全系统控制流",
    "参考 xv6-riscv；单核、无重定向。右侧依次标注特权级、栈、关键自旋锁。",
    [
        ("01 输入", "Shell: gets → read(0,&c,1) → ecall", ["usys 存根把 SYS_read 放入 a7；硬件 U→S，跳 uservec。"], ["U→S｜sh 用户栈→内核栈", "无锁"], "#CF7B43"),
        ("02 等待", "usertrap → syscall → sys_read → consoleread", ["缓冲区未满一行：登记 &cons.r，放 cons.lock，sleep→sched。"], ["S｜sh 内核栈→调度器栈", "cons.lock 已放；切换持 sh.lock"], "#087E83"),
        ("03 键盘", "UART IRQ → kernelvec → devintr → uartintr", ["中断打在空闲 scheduler；consoleintr 收齐换行并 wakeup。"], ["S｜调度器栈（不换栈）", "consoleintr 持 cons.lock"], "#087E83"),
        ("04 恢复", "scheduler 选 sh → consoleread 返回", ["swtch 换回 sh 内核栈；read 每次取 1 字节，gets 拼出整行。"], ["S→U｜内核栈→sh 用户栈", "sh.lock 归还后无锁"], "#087E83"),
        ("05 复制", "sh: fork → sys_fork → kfork", ["复制用户内存、寄存器、ofile；子 a0=0，父 a0=子 pid。"], ["U→S→U｜sh 内核栈", "短暂持子 proc.lock / wait_lock"], "#CF7B43"),
        ("06 分路", "父 sh: wait(0)；子 sh: runcmd", ["父阻塞等子退出；子从 fork 后继续，解析 echo hi。"], ["父 S｜sh 内核栈→调度器栈", "子 U｜子用户栈"], "#087E83"),
        ("07 换镜像", "子: exec(\"echo\") → sys_exec → kexec", ["建新页表、装入 ELF、设新 epc/sp；保留 pid 和 ofile。"], ["U→S→U｜子内核栈→用户栈", "文件系统锁短暂持有"], "#CF7B43"),
        ("08 输出", "echo: main → write(1,\"hi\",2)", ["sys_write → filewrite → consolewrite → uartwrite → UART THR。"], ["U→S→U｜echo 用户/内核栈", "uartwrite 持睡眠锁 tx_lock"], "#087E83"),
        ("09 换行", "echo: write(1,\"\\n\",1)", ["这份 echo.c 是两次 write：一次 hi，一次换行；不是三次。"], ["U→S→U｜echo 用户/内核栈", "同上一条输出链"], "#087E83"),
        ("10 退出", "echo: exit(0) → kexit", ["fileclose 释放 fd 引用；状态变 ZOMBIE，唤醒父进程。"], ["U→S｜echo 内核栈→调度器栈", "切换时只持 echo.lock"], "#CF7B43"),
        ("11 回收", "sh: wait → kwait → freeproc", ["父进程回收 echo 的 trapframe、页表和进程槽位。"], ["S→U｜sh 内核栈→用户栈", "短暂持 wait_lock / 子 proc.lock"], "#087E83"),
    ],
    [
        "① 键盘输入回显也走 UART，但它不是 echo 程序的 write；不要把两种输出混为一谈。",
        "② ecall 走 uservec；空闲调度器收到 UART 中断走 kernelvec。两条入口使用不同的栈。",
        "③ swtch 改变运行栈与上下文，不改变 S 特权级；进程切换必须经过 scheduler。",
    ],
)


d = Drawing(1320, 925, "材料二①｜进程表快照", "截面：子进程 kexec 成功、尚未返回 echo 用户态；典型单核、无重定向、无其他子进程。")
d.box(35, 106, 1250, 90, "截面约定", ["此刻 echo 仍在 sys_exec / usertrap 的 S 态路径上，state=RUNNING；父 sh 和 init 正在 wait 中。", "proc 下标和 pid 是本次无额外进程的示例，不能把它们当作所有运行的固定值。"], "#CF7B43")
headers = [(35, 160, "字段"), (195, 355, "init（示例 proc[0]）"), (550, 355, "sh（示例 proc[1]）"), (905, 380, "echo（示例 proc[2]）")]
for x, width, label in headers:
    d.rect(x, 224, width, 50, fill="#153B45", stroke="#153B45")
    d.text(x + 13, 255, label, 16, "#FFFFFF", "bold")
entries = [
    ("pid", "1", "2", "3"),
    ("state / chan", "SLEEPING / init", "SLEEPING / sh", "RUNNING / 0"),
    ("parent", "0", "init", "sh"),
    ("kstack 基址", "0x3fffffd000", "0x3fffffb000", "0x3fffff9000"),
    ("pagetable", "P_init（独立用户页表）", "P_sh（独立用户页表）", "P_echo（exec 新建）"),
    ("sz", "0x4000", "0x5000", "0x4000"),
    ("ofile[0..2]", "F / F / F", "F / F / F", "F / F / F"),
    ("ofile[3..15]", "均为 0", "均为 0", "均为 0"),
]
for index, row in enumerate(entries):
    y = 274 + index * 62
    for col, (x, width, _) in enumerate(headers):
        d.rect(x, y, width, 62, fill="#FFFFFF" if index % 2 == 0 else "#EDF3F4")
        d.text(x + 13, y + 37, row[col], 15, "#18313B", "bold" if col == 0 else "normal")
d.note(35, 789, 1250, "批注：哪些值是推导，哪些不能写死？", [
    "P_init / P_sh / P_echo 的物理地址由运行时分配，不是固定常数；每个进程有自己的页表。",
    "sz 来自本参考树的 _init、_sh、_echo ELF 与各自 2 页 guard+栈；若二进制重编译，数值需重验。",
])
d.save("图2-材料二-进程表快照.svg")


d = Drawing(1320, 1010, "材料二②｜echo 用户页表快照", "exec 已提交新页表，首条 echo 用户指令尚未运行；地址基于本参考树 _echo ELF。")
d.box(35, 106, 1250, 76, "Sv39 根页表：两条有效分支", ["satp → L2[0] → L1[0] → L0[0..3]；另一路 L2[255] → L1[511] → L0[510..511]。"], "#CF7B43")
d.line(370, 182, 370, 218, arrow=True)
d.line(950, 182, 950, 218, arrow=True)
d.box(35, 220, 600, 117, "低地址分支：用户程序", ["L0[0] 代码；[1] 数据；[2] guard；[3] 用户栈。", "用户可访问的页必须带 U；guard 只清除 U。"], "#087E83")
d.box(685, 220, 600, 117, "高地址分支：陷入桥梁", ["L0[510] trapframe；[511] trampoline。", "都不带 U；trampoline 在内核页表中也有映射。"], "#087E83")
cols = [(35, 280, "用户虚拟地址区间"), (315, 330, "内容"), (645, 280, "叶子 PTE 标志"), (925, 360, "用户能否访问")]
for x, width, title in cols:
    d.rect(x, 360, width, 48, fill="#153B45", stroke="#153B45")
    d.text(x + 12, 391, title, 15, "#FFFFFF", "bold")
mappings = [
    ("0x0000–0x0fff", "代码 / 只读数据", "V R X U = 0x1b", "可读、可执行"),
    ("0x1000–0x1fff", "数据 / BSS", "V R W U = 0x17", "可读、可写"),
    ("0x2000–0x2fff", "用户栈 guard 页", "V R W = 0x07", "不可访问：已映射但无 U"),
    ("0x3000–0x3fff", "用户栈（1 页）", "V R W U = 0x17", "可读、可写"),
    ("0x4000–0x3fffffdfff", "堆起点；此刻无堆页", "无有效 PTE", "sbrk 后才可能映射"),
    ("0x3fffffe000–efff", "trapframe", "V R W = 0x07", "不可访问：仅 S 态使用"),
    ("0x3ffffff000–ffff", "trampoline", "V R X = 0x0b", "不可访问：仅 S 态执行"),
]
for index, row in enumerate(mappings):
    y = 408 + index * 64
    for col, (x, width, _) in enumerate(cols):
        d.rect(x, y, width, 64, fill="#FFFFFF" if index % 2 == 0 else "#EDF3F4")
        d.text(x + 12, y + 39, row[col], 14, "#18313B")
d.note(35, 873, 1250, "批注：guard 与堆最容易画错", [
    "guard 是真实分配的一页，只通过 uvmclear 清掉 PTE_U；它不是一个未映射的洞。",
    "本次 echo 的 sz=0x4000：0x4000 是未来堆增长起点，此刻没有堆的叶子 PTE。",
])
d.save("图3-材料二-页表快照.svg")


d = Drawing(1320, 970, "材料二③｜stdout 文件引用链", "截面同上：init → sh → echo，三个进程均无重定向；各自 fd 0/1/2 指向同一个 file。")
for x, title, detail in [
    (35, "init", ["ofile[0] / [1] / [2] → F", "首次 open + 两次 dup；ref 贡献 3"]),
    (445, "sh", ["ofile[0] / [1] / [2] → F", "fork 继承；ref 贡献 3"]),
    (855, "echo", ["ofile[0] / [1] / [2] → F", "再次 fork；exec 不改 fd；贡献 3"]),
]:
    d.box(x, 125, 390, 126, title, detail, "#CF7B43")
    d.line(x + 195, 252, 660, 334, arrow=True)
d.box(230, 338, 860, 125, "系统 file 表中的同一个 struct file：F", [
    "type=FD_DEVICE；ref=9；major=CONSOLE(1)；readable=1，writable=1。",
    "echo 的 stdout 是 ofile[1]；filewrite 根据 major 查设备函数表。",
], "#087E83")
d.line(660, 464, 660, 514, arrow=True)
d.box(230, 520, 860, 104, "F.ip → struct inode：console", [
    "type=T_DEVICE；major=1，minor=0；inode 身份与 file 引用计数是两回事。",
], "#087E83")
d.line(660, 625, 660, 671, arrow=True)
d.box(230, 676, 860, 110, "F.major=1 → devsw[1].write = consolewrite", [
    "sys_write → filewrite → consolewrite → uartwrite → UART THR (0x10000000)。",
], "#087E83")
d.note(35, 826, 1250, "批注：9 从哪来？退出后怎样释放？", [
    "init 的 open+dup+dup 得 3；fork sh 后 6；fork echo 后 9；exec 不改变 ofile。",
    "echo exit 时 fileclose 三次，F.ref 从 9 变 6；最后一次 close 才通过 iput 释放 inode 引用。",
])
d.save("图4-材料二-文件表快照.svg")


timeline(
    "图5-材料三-时钟中断的微观旅程.svg",
    "材料三｜一次 S 态时钟中断的微观旅程",
    "例：单核 echo 正在 U 态运行；scause=0x8000000000000005；本树使用 stimecmp 直接触发 S 态时钟中断。",
    [
        ("01 触发", "time ≥ stimecmp，CPU 接受时钟中断", ["硬件记 sepc，写 scause=高位1+原因5，SPP=0，关 SIE。"], ["U→S｜暂用 echo 用户栈", "无锁；当前还是用户页表"], "#CF7B43"),
        ("02 保存", "stvec → trampoline:uservec", ["用户通用寄存器保存到 TRAPFRAME；还没有进入 C 代码。"], ["S｜仍用原 sp", "无锁；仍是用户页表"], "#087E83"),
        ("03 换栈表", "uservec 装 kernel_sp，切 kernel_satp", ["sp 改为 echo 内核栈顶；sfence.vma 后进入 usertrap。"], ["S｜echo 内核栈", "无锁；换为内核页表"], "#087E83"),
        ("04 分发", "usertrap 保存 epc；devintr 识别原因 5", ["改 stvec=kernelvec；时钟中断不做 epc+=4。"], ["S｜echo 内核栈", "无锁"], "#087E83"),
        ("05 时钟", "clockintr：ticks++，wakeup，续约", ["hart0 短暂持 tickslock；w_stimecmp(time+1000000)。"], ["S｜echo 内核栈", "tickslock 随即释放"], "#087E83"),
        ("06 让步", "which_dev=2 → yield → sched", ["echo: RUNNING→RUNNABLE；存 context，swtch 到调度器。"], ["S｜echo 内核栈→调度器栈", "只持 echo.lock 跨 swtch"], "#CF7B43"),
        ("07 决策", "scheduler 扫 RUNNABLE 进程", ["选中某进程并 swtch；若仍选 echo，就回到 echo 的 sched。"], ["S｜调度器栈→被选进程栈", "选中时持对应 proc.lock"], "#087E83"),
        ("08 恢复", "echo 重新获选：yield 返回 usertrap", ["释放 echo.lock；prepare_return 配好 stvec、SPP、SPIE、sepc。"], ["S｜echo 内核栈", "无锁；内核页表"], "#087E83"),
        ("09 返回", "trampoline:userret → sret", ["换回 echo 用户页表，恢复寄存器与用户 sp，sret 回原 PC。"], ["S→U｜echo 用户栈", "无锁；用户页表"], "#CF7B43"),
    ],
    [
        "① 中断不跳过被打断的指令；只有 ecall 返回时才把 epc 加 4。",
        "② 时钟中断触发 yield 抢占：状态变 RUNNABLE，不是 SLEEPING；无需 wakeup 即可再运行。",
        "③ 若另一进程先被选中，echo 的现场仍留在 trapframe+内核栈，等再次调度时继续恢复。",
    ],
)
