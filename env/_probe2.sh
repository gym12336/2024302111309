#!/bin/bash
# 检查 apt 里是否有课程需要的包（只读，不安装），以及 sudo 是否需要密码
echo "== sudo 是否可免密 =="
if sudo -n true 2>/dev/null; then echo "免密 sudo：可用"; else echo "免密 sudo：不可用（需要输入密码）"; fi

echo
echo "== 目标软件包在 apt 中的情况 =="
for p in gcc-riscv64-unknown-elf binutils-riscv64-unknown-elf qemu-system-misc; do
  echo "--- $p ---"
  apt-cache policy "$p" 2>/dev/null | head -4 || echo "  查询失败"
done

echo
echo "== 本地包索引是否为空 =="
ls /var/lib/apt/lists/*Packages* >/dev/null 2>&1 \
  && echo "已有包索引（$(ls /var/lib/apt/lists/*Packages* 2>/dev/null | wc -l) 个文件）" \
  || echo "包索引为空，必须先跑 apt update"
