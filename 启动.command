#!/bin/bash
# macOS 一键启动：双击本文件即可。
cd "$(dirname "$0")" || exit 1

PY=""
for c in python3 python3.13 python3.12 python3.11 /usr/bin/python3 /opt/homebrew/bin/python3; do
  if command -v "$c" >/dev/null 2>&1; then PY="$c"; break; fi
done

if [ -z "$PY" ]; then
  echo "未找到 Python 3。请先安装 Python 3.11 或更高版本：https://www.python.org/downloads/"
  echo "安装完成后再次双击本文件。"
  read -r -p "按回车键关闭…" _
  exit 1
fi

echo "使用 $($PY --version)"
"$PY" run.py
echo
read -r -p "服务已停止，按回车键关闭窗口…" _
