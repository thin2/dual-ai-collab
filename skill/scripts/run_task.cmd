@echo off
setlocal
set "PYTHON_BIN=python"
where py >nul 2>nul
if %errorlevel%==0 set "PYTHON_BIN=py -3"

if /I "%~1"=="start" goto start
if /I "%~1"=="status" goto status
if /I "%~1"=="stop" goto stop
echo 用法: run_task.cmd ^<start^|status^|stop^> ...
exit /b 1

:start
%PYTHON_BIN% "%~dp0run_task.py" %*
exit /b %errorlevel%

:status
%PYTHON_BIN% "%~dp0run_task.py" status %2
exit /b %errorlevel%

:stop
%PYTHON_BIN% "%~dp0run_task.py" stop %2
exit /b %errorlevel%
