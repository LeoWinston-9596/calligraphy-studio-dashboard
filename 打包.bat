@echo off
chcp 65001 >nul
rem Windows 一键打包：双击本文件，最后会在 installer_output 里生成安装包。
cd /d "%~dp0"

echo ============================================================
echo   书画室看板 - 打包成 Windows 安装程序
echo ============================================================
echo.

rem 优先用项目自带的虚拟环境，没有就用系统 Python
set "PY="
if exist ".venv\Scripts\python.exe" (
  set "PY=.venv\Scripts\python.exe"
  echo 使用项目虚拟环境 .venv
) else (
  where py >nul 2>&1 && set "PY=py -3"
  if not defined PY (
    where python >nul 2>&1 && set "PY=python"
  )
)

if not defined PY (
  echo [错误] 没找到 Python。请先安装 Python 3.11 或更高版本：
  echo        https://www.python.org/downloads/
  echo        安装时务必勾选 "Add Python to PATH"
  pause
  exit /b 1
)

echo.
echo [1/3] 安装依赖 ...
%PY% -m pip install -q --timeout 30 -r requirements.txt
if errorlevel 1 (
  echo      默认源装不上，换清华镜像重试 ...
  %PY% -m pip install -q --timeout 30 -i https://pypi.tuna.tsinghua.edu.cn/simple ^
       --trusted-host pypi.tuna.tsinghua.edu.cn -r requirements.txt
  if errorlevel 1 (
    echo [错误] 依赖安装失败。请检查网络，或手动执行：
    echo        %PY% -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
    pause
    exit /b 1
  )
)
%PY% -m pip install -q --timeout 30 pyinstaller 2>nul || ^
%PY% -m pip install -q --timeout 30 -i https://pypi.tuna.tsinghua.edu.cn/simple ^
     --trusted-host pypi.tuna.tsinghua.edu.cn pyinstaller

echo.
echo [2/3] 检查语音模型 ...
if not exist "data\models" (
  echo      没有语音模型，正在下载（约 230MB，只需一次）...
  %PY% install_asr.py
)

echo.
echo [3/3] 开始打包（5-15 分钟，请勿关闭窗口）...
%PY% build.py
if errorlevel 1 (
  echo.
  echo [错误] 打包失败，请把上面的报错信息发给技术支持。
  pause
  exit /b 1
)

echo.
echo ============================================================
echo   打包完成
echo ============================================================
echo   安装包在： installer_output\
echo   程序目录在： dist\书画室看板\
echo.
echo   把安装包发给对方，双击安装即可，全程不需要联网。
echo ============================================================
pause
