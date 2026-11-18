@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
if not exist "requirements.txt" goto notextracted

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
  where python >nul 2>nul && set "PY=python"
)
if not defined PY goto nopython

if not exist ".venv\Scripts\python.exe" (
  echo [1/3] 建立 Python 虛擬環境...
  %PY% -m venv .venv
  if errorlevel 1 goto fail
)
echo [2/3] 安裝套件（第一次約需 1-3 分鐘）...
".venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto fail

echo [3/3] 啟動網站 http://localhost:8000 （關閉這個視窗就會停止網站）
start "" cmd /c "timeout /t 5 >nul & start http://localhost:8000"
".venv\Scripts\python.exe" -m uvicorn backend.api.main:app --port 8000
pause
exit /b 0

:nopython
echo 找不到 Python。請到 https://www.python.org/downloads/ 安裝，
echo 安裝畫面記得勾選 "Add python.exe to PATH"，裝好後再雙擊 start.bat。
start "" "https://www.python.org/downloads/"
pause
exit /b 1

:notextracted
echo 找不到專案的其他檔案。看起來是直接在 ZIP 壓縮檔裡執行了 start.bat。
echo 請先對 ZIP 按右鍵 → 「解壓縮全部」，再到解壓縮後的資料夾雙擊 start.bat。
pause
exit /b 1

:fail
echo 發生錯誤，請把這個視窗的訊息截圖給 Claude。
pause
exit /b 1
