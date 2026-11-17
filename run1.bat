@echo off
chcp 65001 >nul
cd /d %~dp0
title KR Screener - run1 (server + browser only)

echo ============================================
echo  KR Screener - run1.bat
echo  1) 데이터 업데이트 안 함 (screener_data.py 실행 안 함)
echo  2) 로컬 서버 시작 (8000)
echo  3) 브라우저 열기 (캐시 방지 ?v=타임스탬프)
echo ============================================
echo.

:: --- data.json 있는지 확인 ---
if not exist data.json (
    echo [오류] data.json이 없습니다.
    echo 먼저 run.bat으로 데이터를 한 번 받아오세요.
    echo.
    pause
    exit /b 1
)
echo data.json 확인됨.
echo.

:: --- 기존 서버 정리 (8000 포트, powershell로만) ---
echo [1/2] 기존 서버 정리 중...
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"
timeout /t 1 /nobreak >nul

:: --- 서버 시작 (백그라운드) ---
echo [2/2] 로컬 서버 시작 중... http://localhost:8000
start "KR Screener Server" /min python -m http.server 8000 --bind 127.0.0.1
timeout /t 2 /nobreak >nul

:: --- 브라우저 열기 (캐시 방지 타임스탬프) ---
for /f %%t in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMddHHmmss"') do set TS=%%t
start "" "http://localhost:8000/screener.html?v=%TS%"

echo.
echo ============================================
echo  완료! 브라우저에서 스크리너가 열렸습니다.
echo  서버를 끄려면 이 창을 닫고, 서버 창(KR Screener Server)도 닫으세요.
echo ============================================
pause
