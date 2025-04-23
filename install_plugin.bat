@echo off
chcp 65001 > nul
REM QGIS 도면 자동화 플러그인 설치 스크립트

echo QGIS 도면 자동화 플러그인 설치를 시작합니다...
echo.

REM QGIS 플러그인 디렉토리 설정
set PLUGIN_DIR=%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\domun_automation_plugin

REM 기존 플러그인 폴더가 있으면 삭제
if exist "%PLUGIN_DIR%" (
    echo 기존 플러그인을 제거하는 중...
    rmdir /s /q "%PLUGIN_DIR%"
)

REM 플러그인 디렉토리 생성
echo 플러그인 디렉토리를 생성하는 중...
mkdir "%PLUGIN_DIR%"

REM 현재 폴더의 모든 파일을 플러그인 디렉토리로 복사
echo 플러그인 파일을 복사하는 중...
xcopy /s /e /y ".\*" "%PLUGIN_DIR%\"

echo.
echo 설치가 완료되었습니다!
echo 설치방법.txt를 한번 읽어보신 뒤 이용하시면 됩니다.
echo QGIS를 재시작한 후 플러그인 관리자에서 '현존식생도플러그인'을 활성화하세요.
echo.
pause