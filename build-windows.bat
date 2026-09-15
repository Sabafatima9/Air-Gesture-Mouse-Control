@echo off
rem Build AirGestureMouse.exe on Windows with PyInstaller (one-file, windowed).
rem Run from the repo root. Requires a project venv with deps + pyinstaller.
setlocal
set "HERE=%~dp0"
cd /d "%HERE%"

if not exist "%HERE%venv\Scripts\python.exe" (
    echo [build-windows.bat] venv not found. Create it first:
    echo     py -3.10 -m venv venv
    echo     venv\Scripts\python -m pip install -r requirements.txt pyinstaller
    pause
    exit /b 1
)

"%HERE%venv\Scripts\python.exe" -m pip install -q pyinstaller
"%HERE%venv\Scripts\python.exe" -m PyInstaller --noconfirm main.spec
if errorlevel 1 (
    echo Build failed.
    pause
    exit /b 1
)

if exist "%HERE%dist\AirGestureMouse.exe" (
    copy /Y "%HERE%dist\AirGestureMouse.exe" "%HERE%AirGestureMouse.exe" >nul
    echo.
    echo Built: dist\AirGestureMouse.exe
    echo Copied to repo root: AirGestureMouse.exe
) else (
    echo Expected dist\AirGestureMouse.exe was not produced.
    pause
    exit /b 1
)
pause
