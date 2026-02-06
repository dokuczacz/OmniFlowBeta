@echo off
setlocal
cd /d "%~dp0"

REM Double-click entrypoint for Windows.
REM Starts Azurite + Azure Functions for OmniFlowCentralRepo (App2).

where py >nul 2>nul
if %ERRORLEVEL%==0 (
  py -3.11 scripts\run_local.py
  goto :done
)

where python >nul 2>nul
if %ERRORLEVEL%==0 (
  python scripts\run_local.py
  goto :done
)

echo ERROR: Neither "py" nor "python" found on PATH.
exit /b 1

:done
endlocal
