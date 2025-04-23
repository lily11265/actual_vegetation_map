# 도면 자동화 플러그인

## 개요
이 플러그인은 QGIS에서 기초 현존식생도를 그려주는 플러그인입니다. 산림청이 제공하는 임상도와 1:25000 토지피복도를 이용해서 그립니다. 

## 주요 기능
- 인덱스 맵을 활용한 도면 자동 로드
- 라인 → 폴리곤 변환
- 도면 클리핑
- 작은 폴리곤 병합
- GRASS v.generalize snakes 알고리즘 적용
- 속성 기반 피처 병합
- 디버그 모드 지원

## 설치 방법

### 자동 설치
1. create_plugin.py 스크립트 실행
2. 프롬프트에 따라 설치 진행
3. QGIS 재시작
4. 플러그인 관리자에서 '도면 자동화 플러그인' 활성화

### 수동 설치
1. 플러그인 폴더를 QGIS 플러그인 디렉토리에 복사
   - Windows: `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins`
   - macOS: `~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins`
   - Linux: `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins`
2. QGIS 재시작
3. 플러그인 관리자에서 활성화

## 사용 방법
1. QGIS에서 처리할 레이어 활성화
2. 플러그인 툴바의 '도면 자동화 실행' 버튼 클릭
3. 처리 진행 상황 확인
4. 완료 후 결과 확인

## 필요 파일
- `TN_MAPINDX_5K25K.gpkg`: 인덱스 맵 파일 (resources 폴더에 포함)
- `big_data_land_25000`: 25000 스케일 데이터 (resources 폴더에 포함)

## 디버그 모드
- 디버그 모드는 기본적으로 활성화됨
- 메뉴에서 '디버그 모드 토글'로 on/off 가능
- 디버그 메시지는 QGIS 메시지 바와 파이썬 콘솔에 표시

## 요구사항
- QGIS 3.0 이상
- GRASS GIS 플러그인
- Python 3.x

## 라이선스
GNU General Public License v2.0

## 작성자
허원석 (wonsukhuh10@gmail.com)

## 버전
1.0

## 업데이트 내역
- 1.0 (2025-04-23): 최초 릴리즈