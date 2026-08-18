@echo off
chcp 65001 >nul
rem Windows 一键启动：双击本文件即可。
cd /d "%~dp0"

set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY (
  where python >nul 2>&1 && set "PY=python"
)

if not defined PY (
  echo 未找到 Python 3。请先安装 Python 3.11 或更高版本：https://www.python.org/downloads/
  echo 安装时请勾选 "Add Python to PATH"，装好后再次双击本文件。
  pause
  exit /b 1
)

%PY% run.py
echo.
echo 服务已停止。
pause
