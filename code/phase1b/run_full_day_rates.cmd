@echo off
cd /d "%MOVES_HOME%"
call setenv.bat
call ant run -Drunspec="%REPO_ROOT%\provenance\phase1b\full_day_rates.mrs" > "%REPO_ROOT%\provenance\phase1b\full_day_rates_console.log" 2>&1
exit /b %errorlevel%
