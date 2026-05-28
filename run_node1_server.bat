@echo off
setlocal
title DistRes Node 1
cd /d "%~dp0"
set "PY_EXE="
call :select_python
if not defined PY_EXE (
    echo Could not find a Python interpreter with FastAPI and Uvicorn installed.
    echo Run this once, then try again:
    echo python -m pip install -r requirements.txt
    pause
    exit /b 1
)
"%PY_EXE%" -c "import sys; print('Using Python: ' + sys.executable)"
echo Starting DistRes node1 on http://127.0.0.1:8001
echo Press Ctrl+C to stop.
echo.
"%PY_EXE%" "app\Run_Servers\Node1_Server_Run.py"
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" (
    echo.
    echo Node 1 stopped with error code %EXIT_CODE%.
    pause
)
exit /b %EXIT_CODE%

:select_python
call :try_python "%~dp0.venv\Scripts\python.exe"
call :try_python python
call :try_python "%LocalAppData%\Programs\Python\Python312\python.exe"
call :try_python "%LocalAppData%\Programs\Python\Python311\python.exe"
exit /b 0

:try_python
if defined PY_EXE exit /b 0
if "%~1"=="python" (
    python -c "import fastapi, uvicorn" >nul 2>nul && set "PY_EXE=python"
    exit /b 0
)
if exist "%~1" (
    "%~1" -c "import fastapi, uvicorn" >nul 2>nul && set "PY_EXE=%~1"
)
exit /b 0
