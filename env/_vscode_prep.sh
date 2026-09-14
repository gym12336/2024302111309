#!/bin/bash
# WSL 侧为 VSCode 集成做准备：检查 code 命令桥接、必要依赖
set -u

echo "===== 1. WSL 内是否已有 code 命令桥 ====="
p=$(command -v code 2>/dev/null)
if [ -n "$p" ]; then
  echo "[ ok ] code -> $p"
else
  echo "[--] WSL 内暂无 code 命令（装好 WSL 扩展并从 VSCode 连过一次后会自动注入）"
fi

echo
echo "===== 2. VSCode Server 依赖检查 ====="
# VSCode 在 WSL 内会自动下载 server，需要这些基础库
for c in wget curl tar gzip; do
  if command -v "$c" >/dev/null 2>&1; then
    printf '[ ok ] %s\n' "$c"
  else
    printf '[MISSING] %s  (VSCode Server 下载/解压可能受影响)\n' "$c"
  fi
done
echo "libstdc++ 版本（server 需要较新的 GLIBCXX）："
strings /usr/lib/x86_64-linux-gnu/libstdc++.so.6 2>/dev/null | grep -oE 'GLIBCXX_3\.4\.[0-9]+' | sort -V | tail -3 | sed 's/^/        /'

echo
echo "===== 3. 是否已存在 VSCode Server ====="
for d in ~/.vscode-server ~/.vscode-server-insiders ~/.cursor-server; do
  if [ -d "$d" ]; then
    echo "[存在] $d  (大小: $(du -sh "$d" 2>/dev/null | cut -f1))"
  fi
done
[ -d ~/.vscode-server ] || echo "[--] ~/.vscode-server 尚未创建（首次连接时自动生成）"

echo
echo "===== 4. 工作目录状态 ====="
echo "路径: $HOME/oslab"
ls -la ~/oslab 2>/dev/null | tail -n +2

echo
echo "===== 5. WSL 内网络（VSCode Server 需从微软 CDN 下载 ~50MB）====="
code_test=$(curl -s -o /dev/null -w '%{http_code}' -m 8 https://update.code.visualstudio.com/ 2>/dev/null)
echo "update.code.visualstudio.com -> HTTP ${code_test:-FAIL}"
