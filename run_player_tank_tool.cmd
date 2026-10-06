@echo off
title SABoW player tank tool
rem Runs the tool that sits BESIDE this file.
rem It used to do "cd /d K:\DeepseekSABoW" and then run player_tank_tool.py from there -
rem a file that is not in that folder, so this launcher failed even on the development
rem machine. It also called bare "python", which is not on PATH on many Windows boxes.
rem Release audit 2026-10-06, docs\RELEASE_AUDIT_2026-10-06.md B2.
cd /d "%~dp0"

if not exist "%~dp0player_tank_tool.py" (
    echo.
    echo player_tank_tool.py is not in this folder:
    echo     %~dp0
    echo Keep this .cmd next to the tool files.
    echo.
    pause
    exit /b 1
)

rem && runs the set only if where succeeded, which avoids %ERRORLEVEL% being expanded
rem when the block is PARSED rather than when it runs - the usual batch trap.
set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY where python >nul 2>&1 && set "PY=python"
if not defined PY (
    echo.
    echo Python 3 was not found on this PC.
    echo Install it from https://www.python.org/downloads/ and tick
    echo "Add python.exe to PATH" during setup, then run this again.
    echo.
    pause
    exit /b 1
)

%PY% "%~dp0player_tank_tool.py"
echo.
echo ---- finished, exit code %ERRORLEVEL% ----
pause
