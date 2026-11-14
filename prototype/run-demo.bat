@echo off
REM Starts the Chrome & Oak prototype on Windows: API on port 8000, UI on port 5173, then opens the browser.
REM First run installs the Python and Node dependencies.
cd /d "%~dp0"
if not exist .venv (
  python -m venv .venv
  .venv\Scripts\python.exe -m pip install -q -r api\requirements.txt
)
if not exist ui\node_modules (
  pushd ui
  call npm install
  popd
)
start "API :8000" cmd /k ".venv\Scripts\python.exe -m uvicorn api.main:app --port 8000"
start "UI :5173" cmd /k "cd ui && npm run dev"
timeout /t 8 /nobreak >nul
start "" http://localhost:5173/
