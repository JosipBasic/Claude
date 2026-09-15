@echo off
REM Build adman.exe on Windows. Run this from the adman\ directory.
REM PyInstaller does not cross-compile, so this must be run on a Windows
REM machine (the target Windows Server works too, or any Windows box with
REM the same architecture/bitness you plan to deploy to).

setlocal

python -m venv .venv-build
call .venv-build\Scripts\activate.bat

pip install -r requirements-build.txt
pyinstaller adman.spec

echo.
echo Build complete: dist\adman\adman.exe
echo Copy the whole dist\adman\ folder to the target server and run adman.exe from inside it.
endlocal
