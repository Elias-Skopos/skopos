@echo off
setlocal
cd /d "%~dp0"
"%~dp0.venv\Scripts\python.exe" "%~dp0local_postgres.py" start
if errorlevel 1 goto failure
"%~dp0.venv\Scripts\python.exe" "%~dp0local_postgres.py" backup
if errorlevel 1 goto failure
"%~dp0.venv\Scripts\python.exe" -m streamlit run "%~dp0app.py" --server.address 127.0.0.1
exit /b %errorlevel%
:failure
echo Nao foi possivel preparar o banco local. Consulte POSTGRESQL_LOCAL.md.
pause
exit /b 1
