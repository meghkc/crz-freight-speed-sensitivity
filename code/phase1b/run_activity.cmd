@echo off
cd /d "%MOVES_HOME%"
call setenv.bat
call ant run -Drunspec="%REPO_ROOT%\provenance\phase1b\activity_run.mrs" > "%REPO_ROOT%\provenance\phase1b\activity_console.log" 2>&1
exit /b %errorlevel%
