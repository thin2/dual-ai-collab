@echo off
setlocal
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 "%~dp0verify_task.py" %*
) else (
  python "%~dp0verify_task.py" %*
)
