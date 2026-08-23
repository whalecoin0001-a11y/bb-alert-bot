@echo off
setlocal
cd /d "%~dp0"

set PYEXE=
if exist "C:\Windows\py.exe" set PYEXE=C:\Windows\py.exe
if "%PYEXE%"=="" (
    where py.exe >nul 2>nul
    if %errorlevel%==0 set PYEXE=py
)
if "%PYEXE%"=="" (
    where python.exe >nul 2>nul
    if %errorlevel%==0 set PYEXE=python
)
if "%PYEXE%"=="" (
    echo Python not found
    exit /b 1
)

%PYEXE% check_bb.py >> check_log.txt 2>&1
