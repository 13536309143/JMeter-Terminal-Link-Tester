@echo off
setlocal
set "LINKLAB_WORKSPACE=%~dp0"
"%~dp0.venv\Scripts\python.exe" -m linklab.production_cli %*
exit /b %ERRORLEVEL%
