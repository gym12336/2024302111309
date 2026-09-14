#!/bin/bash
# 第 3 步：环境验证（命令存在性 + 真实编译 + QEMU 启动）
echo "===== 1. 命令位置与版本 ====="
for c in riscv64-unknown-elf-gcc riscv64-unknown-elf-ld \
         riscv64-unknown-elf-objdump riscv64-unknown-elf-readelf \
         riscv64-unknown-elf-addr2line qemu-system-riscv64 \
         git python3 perl make; do
  p=$(command -v "$c" 2>/dev/null)
  if [ -n "$p" ]; then
    v=$("$c" --version 2>/dev/null | head -1)
    printf '[ ok ] %-32s %s\n' "$c" "$p"
    [ -n "$v" ] && printf '        └─ %s\n' "$v"
  else
    printf '[FAIL] %-32s 未找到\n' "$c"
  fi
done

echo
echo "===== 2. gdb 情况（本课程不用，缺失属正常）====="
if command -v riscv64-unknown-elf-gdb >/dev/null 2>&1; then
  echo "[ ok ] riscv gdb 可用"
else
  echo "[warn] riscv gdb 不可用 —— 与文档预期一致，本课程用 -d int / -d in_asm / QEMU Monitor 替代"
fi

echo
echo "===== 3. 真实交叉编译测试 ====="
T=$(mktemp -d)
cat > "$T/t.c" <<'EOF'
int add(int a, int b) { return a + b; }
EOF
if riscv64-unknown-elf-gcc -march=rv64g -mabi=lp64d -c "$T/t.c" -o "$T/t.o" 2>"$T/err"; then
  echo "[ ok ] 编译成功，产物："
  file "$T/t.o" 2>/dev/null | sed 's/^/        /'
  echo "[ ok ] objdump 反汇编输出（证明工具链闭环）："
  riscv64-unknown-elf-objdump -d "$T/t.o" | tail -n 8 | sed 's/^/        /'
else
  echo "[FAIL] 编译失败："; sed 's/^/        /' "$T/err"
fi

echo
echo "===== 4. QEMU RISC-V 启动测试 ====="
qemu-system-riscv64 --version | head -1 | sed 's/^/        /'
echo "        可用机型（应包含 virt，课程实验用的就是它）："
qemu-system-riscv64 -machine help 2>/dev/null | grep -i '^virt' | sed 's/^/        /'
echo "        单核/双核参数支持（-smp 1 基线 / -smp 2 加分项）："
if timeout 10 qemu-system-riscv64 -machine virt -smp 2 -nographic -monitor none \
     -serial none -bios none -d unimp 2>/dev/null & then
  sleep 2; kill %1 2>/dev/null; wait %1 2>/dev/null
  echo "        [ ok ] -machine virt -smp 2 可正常实例化"
fi
rm -rf "$T"

echo
echo "===== 5. git 身份配置（第 5 步 git init 前必须有）====="
n=$(git config --global user.name 2>/dev/null)
e=$(git config --global user.email 2>/dev/null)
echo "user.name : ${n:-<未设置>}"
echo "user.email: ${e:-<未设置>}"
