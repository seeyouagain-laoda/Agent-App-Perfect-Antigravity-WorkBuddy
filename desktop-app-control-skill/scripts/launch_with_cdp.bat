@echo off
setlocal

REM ============================================================
REM Generic CDP launcher template for Electron / Chromium apps.
REM Copy this file, then edit APP_EXE and APP_ARGS below.
REM MUST be CRLF + pure ASCII + absolute exe path.
REM ============================================================

set PORT=9333
set APP_EXE="C:\path\to\your\app.exe"
set APP_ARGS=--remote-debugging-port=%PORT%

REM Kill any previous instance by exe name to avoid port conflict.
for %%I in (%APP_EXE%) do set APP_NAME=%%~nI
taskkill /IM "%APP_NAME%.exe" /F >nul 2>&1

REM Launch with absolute path and the CDP port.
start "" %APP_EXE% %APP_ARGS%

REM Poll until the CDP endpoint answers.
set /a TRIES=0
:wait
set /a TRIES+=1
curl -s --noproxy "*" http://127.0.0.1:%PORT%/json/version >nul 2>&1
if %ERRORLEVEL%==0 goto ok
if %TRIES% GEQ 30 (
  echo [ERROR] CDP port %PORT% not ready after 30 tries. See %TEMP%\cdp_launch.log
  exit /b 1
)
timeout /t 1 >nul
goto wait

:ok
echo [OK] CDP ready at http://127.0.0.1:%PORT%/json/version
echo Open http://127.0.0.1:%PORT% in a browser to list pages.
