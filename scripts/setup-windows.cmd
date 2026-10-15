@echo off
setlocal
where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  py -3 "%~dp0bootstrap.py" %*
) else (
  python "%~dp0bootstrap.py" %*
)
exit /b %ERRORLEVEL%
