@echo off
chcp 65001 >nul
cd /d %~dp0
title KR Screener - run (update + server + browser)

echo ============================================
echo  KR Screener - run.bat
echo  1) screener_data.py 실행 (스마트 업데이트)
echo  2) 로컬 서버 시작 (8000)
echo  3) 브라우저 열기 (캐시 방지 ?v=타임스탬프)
echo ============================================
echo.

:: --- Python 버전 확인 (wmic 사용 안 함, powershell 사용) ---
for /f "tokens=*" %%v in ('powershell -NoProfile -Command "python --version 2>&1"') do set PYVER=%%v
echo Python: %PYVER%
echo.

:: --- 1) 데이터 업데이트 ---
echo [1/3] 데이터 업데이트 중... (최신이면 자동 스킵됩니다)
python screener_data.py
if errorlevel 1 (
    echo.
    echo [경고] screener_data.py 실행 중 오류가 있었습니다. 기존 data.json으로 계속 진행합니다.
)
echo.

:: --- 2) 기존 서버 정리 (8000 포트, powershell로만) ---
echo [2/3] 기존 서버 정리 중...
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"
timeout /t 1 /nobreak >nul

:: --- 서버 시작 (백그라운드) ---
echo 로컬 서버 시작 중... http://localhost:8000
start "KR Screener Server" /min python -m http.server 8000 --bind 127.0.0.1
timeout /t 2 /nobreak >nul

:: --- 3) 브라우저 열기 (캐시 방지 타임스탬프) ---
echo [3/3] 브라우저 여는 중...
for /f %%t in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMddHHmmss"') do set TS=%%t
start "" "http://localhost:8000/screener.html?v=%TS%"

echo.
echo ============================================
echo  완료! 브라우저에서 스크리너가 열렸습니다.
echo  서버를 끄려면 이 창을 닫고, 서버 창(KR Screener Server)도 닫으세요.
echo ============================================
pause
