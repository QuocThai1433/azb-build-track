@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PY=python"
where py >nul 2>nul
if %errorlevel%==0 (
  py -3.12 --version >nul 2>nul
  if %errorlevel%==0 (
    set "PY=py -3.12"
  ) else (
    set "PY=py"
  )
)
echo Python se duoc su dung: %PY%
if not exist .venv (
  echo [1/3] Tao moi truong Python .venv...
  %PY% -m venv .venv
  if %errorlevel% neq 0 (
    echo Khong tao duoc moi truong ao Python. Hay cai Python 3.11 tro len va thu lai.
    pause
    exit /b 1
  )
)
call .venv\Scripts\activate.bat
echo [2/3] Cai cac thu vien can thiet...
python -m pip install -r requirements.txt
if %errorlevel% neq 0 (
  echo Khong cai duoc thu vien. Hay kiem tra ket noi internet/proxy cua cong ty.
  pause
  exit /b 1
)
echo [3/3] Mo ung dung tai http://127.0.0.1:5000
python app.py
pause
