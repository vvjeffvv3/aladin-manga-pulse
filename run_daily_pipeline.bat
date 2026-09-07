@echo off
chcp 65001 >nul
setlocal

set "PROJECT_DIR=%~dp0"
set "PYTHON=%PROJECT_DIR%aladin_django\.venv\Scripts\python.exe"
set "LOG_DIR=%PROJECT_DIR%logs"
set "LOG_FILE=%LOG_DIR%\daily_pipeline.log"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
cd /d "%PROJECT_DIR%"

echo.>>"%LOG_FILE%"
echo [%date% %time%] START>>"%LOG_FILE%"
echo [%date% %time%] CRAWL START>>"%LOG_FILE%"

"%PYTHON%" -u "%PROJECT_DIR%aladin_manga_scraper.py" >>"%LOG_FILE%" 2>&1
if errorlevel 1 goto failed
echo [%date% %time%] CRAWL DONE>>"%LOG_FILE%"

echo [%date% %time%] GOLD START>>"%LOG_FILE%"
"%PYTHON%" -u "%PROJECT_DIR%gold_transform.py" >>"%LOG_FILE%" 2>&1
if errorlevel 1 goto failed
echo [%date% %time%] GOLD DONE>>"%LOG_FILE%"

echo [%date% %time%] MYSQL START>>"%LOG_FILE%"
"%PYTHON%" -u "%PROJECT_DIR%mysql_loader.py" >>"%LOG_FILE%" 2>&1
if errorlevel 1 goto failed
echo [%date% %time%] MYSQL DONE>>"%LOG_FILE%"

echo [%date% %time%] SUCCESS>>"%LOG_FILE%"
exit /b 0

:failed
set "EXIT_CODE=%errorlevel%"
echo [%date% %time%] FAILED (exit=%EXIT_CODE%)>>"%LOG_FILE%"
exit /b %EXIT_CODE%
