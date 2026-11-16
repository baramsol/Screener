@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 현재 폴더: %CD%
echo ==========================================
echo  Korean Stock Screener 실행 중... (데이터 갱신 없음, 캐시 방지)
echo ==========================================
echo.

if not exist data.json (
  echo [경고] data.json이 없습니다! 먼저 run.bat을 실행하세요.
  pause
  exit /b
)
if not exist screener.html (
  echo [경고] screener.html이 없습니다!
  pause
  exit /b
)

REM --- 캐시 방지 서버 만들기 (매번 새로 생성) ---
REM python 기본 http.server는 캐시를 막아주지 않아서, no-store 헤더를 보내는 서버로 교체
echo import http.server, socketserver, os > serve_nocache.py
echo os.chdir(os.path.dirname(os.path.abspath(__file__)) or '.') >> serve_nocache.py
echo class H(http.server.SimpleHTTPRequestHandler): >> serve_nocache.py
echo     def end_headers(self): >> serve_nocache.py
echo         self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0') >> serve_nocache.py
echo         self.send_header('Pragma', 'no-cache') >> serve_nocache.py
echo         self.send_header('Expires', '0') >> serve_nocache.py
echo         super().end_headers() >> serve_nocache.py
echo     def log_message(self, *a): >> serve_nocache.py
echo         pass >> serve_nocache.py
echo socketserver.TCPServer.allow_reuse_address = True >> serve_nocache.py
echo socketserver.TCPServer(('127.0.0.1', 8000), H).serve_forever() >> serve_nocache.py

echo data.json 확인됨. 서버를 켭니다... (캐시 방지 모드)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do taskkill /F /PID %%a >nul 2>&1
start /min python serve_nocache.py
timeout /t 2 /nobreak >nul

REM --- 매번 다른 주소로 열기 (캐시 완전 방지) ---
REM 시간으로 버전 만들기: 20261117_123456
for /f "tokens=2 delims==" %%i in ('wmic os get localdatetime /value') do set DT=%%i
set VER=%DT:~0,8%_%DT:~8,6%
echo 브라우저를 엽니다... (버전: %VER%)
start http://localhost:8000/screener.html?v=%VER%
echo.
echo ==========================================
echo  이 창을 닫으면 서버가 꺼집니다. 닫지 마세요.
echo  종료하려면 이 창에서 Ctrl+C를 누르세요.
echo  이제 F5를 눌러도 항상 최신 html이 보입니다.
echo ==========================================
pause
