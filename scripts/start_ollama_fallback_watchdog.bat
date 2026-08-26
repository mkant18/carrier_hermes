@echo off
REM Start the Ollama fallback watchdog for OpenMausBot worker bots
REM Runs in background, logs to %USERPROFILE%\.openmausbot\ollama_fallback_watchdog.log
REM
REM Drop this bat file alongside the watchdog script and run it, or register
REM it with Task Scheduler (trigger: At Startup, action: this file).

set "SCRIPT=%~dp0ollama_fallback_watchdog.py"
set "LOG=%USERPROFILE%\.openmausbot\ollama_fallback_watchdog.log"

echo Starting Ollama fallback watchdog...
echo Logging to: %LOG%
echo Script: %SCRIPT%

python "%SCRIPT%" --interval 30 >> "%LOG%" 2>&1
