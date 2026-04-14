@echo off
setlocal
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 "%~dp0task_manager.py" checkpoint-check %*
) else (
  python "%~dp0task_manager.py" checkpoint-check %*
)
