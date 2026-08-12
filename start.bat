@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1
echo Starting EasyReporter...
echo.
echo [DEBUG] Current working directory: %~dp0
echo [DEBUG] Checking Python runtime...
REM Set the current directory as the working directory
cd /d "%~dp0"

REM Prefer bundled python_runtime; fall back to .venv; ensure base runtime completeness
set "APP_DIR=%~dp0"
set "PY_HOME=%APP_DIR%python_runtime"
set "PYTHON_EXE="
set "RUNTIME_TYPE="

if exist "%PY_HOME%\python.exe" (
    echo [DEBUG] Found base Python: %PY_HOME%\python.exe
    set "PYTHON_EXE=%PY_HOME%\python.exe"
    set "RUNTIME_TYPE=base"
) else (
    rem Windows batch doesn't support "else if" on the same line; nest the check instead
    if exist "%PY_HOME%\Scripts\python.exe" (
        echo [DEBUG] Found venv Python: %PY_HOME%\Scripts\python.exe
        set "PYTHON_EXE=%PY_HOME%\Scripts\python.exe"
        set "RUNTIME_TYPE=venv"
    ) else (
        echo [DEBUG] No bundled Python runtime found
    )
)

REM If base runtime selected, verify essential files exist
if /I "%RUNTIME_TYPE%"=="base" (
    REM Check for critical dependencies instead of standard library
    if not exist "%PY_HOME%\Lib\site-packages\streamlit" (
        echo Warning: bundled python_runtime seems incomplete ^(missing streamlit^). Falling back...
        set "PYTHON_EXE="
        set "RUNTIME_TYPE="
    )
)

REM Note: .venv fallback removed - not portable for distribution
REM Users should only rely on bundled python_runtime

if not defined PYTHON_EXE (
    echo [ERROR] No usable Python runtime found!
    echo.
    echo The bundled python_runtime is incomplete or missing.
    echo Please ensure the following exists:
    echo   - python_runtime\python.exe
    echo   - python_runtime\Lib\site-packages\streamlit
    echo.
    pause
    exit /b 1
)

echo [INFO] Using Python runtime: %RUNTIME_TYPE% ^(%PYTHON_EXE%^)
REM If using base python_runtime, make it self-contained
if /I "%RUNTIME_TYPE%"=="base" (
    echo [DEBUG] Setting PYTHONHOME=%PY_HOME%
    set "PYTHONHOME=%PY_HOME%"
    set "PYTHONPATH=%PY_HOME%\Lib;%PY_HOME%\Lib\site-packages"
    echo [DEBUG] Setting PYTHONPATH=%PYTHONPATH%
)

REM Start the Streamlit application
echo Starting EasyReporter application...
echo You can access the application at: http://localhost:8501
echo Press Ctrl+C to stop the application
echo.

echo [DEBUG] Launch command: "%PYTHON_EXE%" -m streamlit run streamlit_app.py --server.port=8501 --server.address=localhost
echo.
"%PYTHON_EXE%" -m streamlit run streamlit_app.py --server.port=8501 --server.address=localhost
set "EXIT_CODE=%ERRORLEVEL%"
echo.
echo [DEBUG] Streamlit exit code: %EXIT_CODE%

if %EXIT_CODE% neq 0 (
    echo [ERROR] Application failed to start! Please check the error messages above.
    echo.
    echo Common troubleshooting:
    echo 1. Check if Python runtime is complete
    echo 2. Check if streamlit_app.py exists
    echo 3. Check if dependencies are installed correctly
    echo.
) else (
    echo [INFO] Application exited normally.
)

echo.
echo Press any key to exit...
pause >nul
exit /b %EXIT_CODE%