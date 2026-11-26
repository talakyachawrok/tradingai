# Local Development Launcher for AI Trading Analyzer (Windows PowerShell)
$root = Split-Path -Parent $PSScriptRoot
Write-Host "Starting AI Trading Analyzer backend on http://127.0.0.1:8000 ..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\backend'; .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"

Write-Host "Starting AI Trading Analyzer frontend on http://localhost:5173 ..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\frontend'; npm run dev"
