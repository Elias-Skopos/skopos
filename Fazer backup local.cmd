@echo off
setlocal
cd /d "%~dp0"
"%~dp0.venv\Scripts\python.exe" "%~dp0local_postgres.py" backup
if errorlevel 1 goto failure
echo Backup concluido na pasta backup_local_postgres.
pause
exit /b 0
:failure
echo O backup nao foi concluido. Consulte POSTGRESQL_LOCAL.md.
pause
exit /b 1
