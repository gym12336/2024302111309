#!/bin/bash
# 环境摸底脚本：在 WSL Ubuntu 内运行
echo "== 身份与系统 =="
echo "user   : $(whoami)"
echo "home   : $HOME"
echo "arch   : $(uname -m)"
echo "kernel : $(uname -r)"
if [ -r /etc/os-release ]; then
  . /etc/os-release
  echo "distro : $PRETTY_NAME"
  echo "codename: $VERSION_CODENAME"
fi

echo
echo "== 已有工具 =="
for c in git python3 perl make gcc gdb \
         riscv64-unknown-elf-gcc riscv64-unknown-elf-ld \
         riscv64-unknown-elf-objdump qemu-system-riscv64; do
  p=$(command -v "$c" 2>/dev/null)
  if [ -n "$p" ]; then echo "[ok]      $c -> $p"; else echo "[MISSING] $c"; fi
done

echo
echo "== 磁盘空间 =="
df -h / | tail -n +1

echo
echo "== apt 源 =="
grep -rhoE '^(deb|Types:|URIs:).*' /etc/apt/sources.list /etc/apt/sources.list.d/ 2>/dev/null | head -12

echo
echo "== 网络连通性（5 秒超时）=="
echo "proxy env: http_proxy=${http_proxy:-<none>} https_proxy=${https_proxy:-<none>}"
if command -v curl >/dev/null 2>&1; then
  code=$(curl -s -o /dev/null -w '%{http_code}' -m 5 http://archive.ubuntu.com/ 2>/dev/null)
  echo "archive.ubuntu.com  -> HTTP ${code:-FAIL}"
  code=$(curl -s -o /dev/null -w '%{http_code}' -m 5 https://mirrors.tuna.tsinghua.edu.cn/ 2>/dev/null)
  echo "mirrors.tuna(清华)  -> HTTP ${code:-FAIL}"
else
  echo "curl 未安装，跳过"
fi
