@echo off
chcp 65001 >nul
echo ==========================================
echo  Korean Stock Screener 실행 중...
echo ==========================================
echo.
if not exist data.json (
  echo [경고] data.json이 없습니다!
  echo 먼저 python screener_data.py 를 실행해서 data.json을 만드세요.
  echo.
  pause
  exit /b
)
if not exist screener.html (
  echo [경고] screener.html이 없습니다!
  pause
  exit /b
)
echo data.json 확인됨. 서버를 먼저 켭니다...
start /min python -m http.server 8000
echo 서버 켜지는 중... 2초 대기
timeout /t 2 /nobreak >nul
echo 브라우저를 엽니다...
start http://localhost:8000/screener.html
echo.
echo 이 창을 닫으면 서버가 꺼집니다. 닫지 마세요.
echo 종료하려면 이 창에서 Ctrl+C를 누르세요.
pause
