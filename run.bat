@echo off
rem Run Air Gesture Mouse Control with the project venv (no activation needed).
setlocal
set "HERE=%~dp0"
if not exist "%HERE%venv\Scripts\python.exe" (
    echo [run.bat] venv not found at "%HERE%venv".
    echo Create it first:
    echo     py -3.13 -m venv venv
    echo     venv\Scripts\python -m pip install -r requirements.txt
    pause
    exit /b 1
)
"%HERE%venv\Scripts\python.exe" "%HERE%main.py" %*
pause
