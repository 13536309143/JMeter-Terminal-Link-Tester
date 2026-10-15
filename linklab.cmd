@echo off
setlocal
set "LINKLAB_WORKSPACE=%~dp0"
"%~dp0.venv\Scripts\python.exe" -m linklab %*
exit /b %ERRORLEVEL%
