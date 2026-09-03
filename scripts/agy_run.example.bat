@echo off
REM ============================================================
REM  Antigravity (agy) Route B 一键入口 —— 示例（公开仓库版）
REM  请先把下面 PY / SCRIPT 改成本机实际路径：
REM    PY     = 你的 Python 解释器（建议隔离 venv，需装 psutil/pywinauto 等）
REM    SCRIPT = 本仓库 scripts\run_agy.py 的绝对路径
REM  用法：
REM    1) 双击本 bat -> 交互输入任务 -> 回车即跑
REM    2) 把任务 .txt 拖到本 bat 上 -> 自动读取并跑
REM ============================================================
set "PY=python"
set "SCRIPT=%~dp0run_agy.py"
if "%~1"=="" (
    "%PY%" "%SCRIPT%"
) else (
    "%PY%" "%SCRIPT%" --file "%~1"
)
if "%~1"=="" pause
