#!/bin/bash
# 第 4 步：建立工作目录、配置 git 非个人项、实测跨文件系统 I/O 差异
set -u

echo "===== 1. 建立课程工作目录 ====="
mkdir -p ~/oslab
cd ~/oslab || exit 1
echo "工作目录：$(pwd)"
echo "所在文件系统：$(df -h --output=source,fstype,avail . | tail -1)"

echo
echo "===== 2. git 全局默认项（非个人信息部分）====="
git config --global init.defaultBranch master
git config --global core.autocrlf false
git config --global core.filemode true
git config --global pull.rebase false
echo "init.defaultBranch = $(git config --global init.defaultBranch)"
echo "core.autocrlf      = $(git config --global core.autocrlf)   # 保持 LF，防止 Windows 换行污染汇编/Makefile"
echo "core.filemode      = $(git config --global core.filemode)"

echo
echo "===== 3. 实测 I/O：WSL 原生 vs /mnt/d（验证文档的 10 倍说法）====="
bench() {
  local dir="$1" label="$2"
  mkdir -p "$dir/_iotest" 2>/dev/null || { echo "  $label: 无法写入，跳过"; return; }
  local start end
  start=$(date +%s.%N)
  for i in $(seq 1 300); do echo "x" > "$dir/_iotest/f$i.tmp"; done
  sync
  end=$(date +%s.%N)
  printf '  %-24s 建 300 个小文件耗时 %.2f 秒\n' "$label" "$(echo "$end - $start" | bc)"
  rm -rf "$dir/_iotest"
}
bench "$HOME"     "WSL 原生 (~/)"
bench "/mnt/d"    "Windows 盘 (/mnt/d)"

echo
echo "===== 4. 当前 git 身份状态 ====="
echo "user.name : $(git config --global user.name  || echo '<未设置>')"
echo "user.email: $(git config --global user.email || echo '<未设置>')"

echo
echo "===== 5. 目录清单 ====="
ls -la ~/oslab
