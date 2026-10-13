@echo off
setlocal
cd /d "%~dp0"
"%~dp0.venv\Scripts\python.exe" "%~dp0local_launcher.py"
if errorlevel 1 goto failure
exit /b %errorlevel%
:failure
echo Nao foi possivel abrir o aplicativo. Consulte a mensagem acima e POSTGRESQL_LOCAL.md.
pause
exit /b 1
