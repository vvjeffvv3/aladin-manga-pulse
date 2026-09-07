# 알라딘 만화 프로젝트 실행 설명서

## 1. 문서 목적

이 문서는 Windows 환경에서 알라딘 만화 데이터를 수집하고 Django 대시보드에 반영하는 전체 실행 절차를 설명한다.

```text
크롤링 → Silver history 누적 → Gold 변환 → MySQL 적재 → Django 확인
```

프로젝트 기준 경로는 다음과 같다.

```text
C:\Users\Playdata\Documents\ChatGPT\개인\aladin_project
```

실제 Windows 파일명에는 밑줄 앞에 백슬래시를 넣지 않는다.

```text
aladin_project       # 올바름
aladin\_project      # 잘못된 경로
```

## 2. 사전 준비

### 2.1 필요한 구성요소

- Windows 10 또는 Windows 11
- Python 가상환경
- 인터넷 연결
- 실행 중인 MySQL 서버
- 알라딘 HTML 페이지에 접근 가능한 네트워크
- Django용 `mysqlclient`
- 적재기용 `mysql-connector-python`
- `.env` 설정을 읽는 `python-dotenv`

현재 가상환경은 다음 위치에 있다.

```text
aladin_project\aladin_django\.venv
```

### 2.2 가상환경 활성화

PowerShell을 열고 다음을 실행한다.

```powershell
cd "C:\Users\Playdata\Documents\ChatGPT\개인\aladin_project\aladin_django"
.\.venv\Scripts\Activate.ps1
cd ..
```

프롬프트 앞에 `(.venv)`가 보이면 활성화된 상태다.

현재 사용 중인 Python을 확인한다.

```powershell
python -c "import sys; print(sys.executable)"
```

정상적인 결과는 다음과 비슷해야 한다.

```text
C:\Users\Playdata\Documents\ChatGPT\개인\aladin_project\aladin_django\.venv\Scripts\python.exe
```

### 2.3 의존성 설치

프로젝트 루트에서 다음을 실행한다.

```powershell
python -m pip install -r .\aladin_django\requirements.txt
```

`mysql_loader.py`를 실행할 때 `No module named 'mysql'` 오류가 나오면 현재 활성화된 동일한 가상환경에서 다음을 추가 실행한다.

```powershell
python -m pip install mysql-connector-python
```

설치 여부는 비밀번호를 출력하지 않고 다음처럼 확인할 수 있다.

```powershell
python -c "import mysql.connector; print('mysql connector OK')"
```

`mysqlclient`와 `mysql-connector-python`은 역할이 다르다.

| 패키지 | 사용하는 곳 |
|---|---|
| `mysqlclient` | Django의 MySQL 데이터베이스 백엔드 |
| `mysql-connector-python` | `mysql_loader.py`의 직접 MySQL 연결 |
| `python-dotenv` | Django·적재기가 프로젝트 루트 `.env`를 읽도록 지원 |

## 3. MySQL 연결 설정

`settings.py`와 `mysql_loader.py`는 프로젝트 루트의 `.env`를 먼저 읽고, 같은 이름의 운영체제 환경변수가 있으면 그 값을 우선 사용한다.

파일 위치:

```text
C:\Users\Playdata\Documents\ChatGPT\개인\aladin_project\.env
```

`.env.example`을 복사해 `.env`를 만들고 비밀번호를 입력한다.

```powershell
cd "C:\Users\Playdata\Documents\ChatGPT\개인\aladin_project"
Copy-Item .env.example .env
notepad .env
```

`.env`의 형식은 다음과 같다.

```env
ALADIN_MYSQL_HOST=127.0.0.1
ALADIN_MYSQL_PORT=3306
ALADIN_MYSQL_USER=root
ALADIN_MYSQL_PASSWORD=여기에_본인_비밀번호
ALADIN_MYSQL_DATABASE=aladin_manga
```

`.env`는 비밀번호가 들어가므로 외부에 공유하거나 Git에 커밋하지 않는다. 기존 PowerShell 환경변수를 사용하고 싶다면 그대로 사용할 수 있지만, 작업 스케줄러 재현성을 위해 `.env`를 기준으로 관리하는 것을 권장한다.

설정 여부만 확인하려면 비밀번호를 출력하지 않고 다음을 실행한다.

```powershell
python -c "from dotenv import load_dotenv; import os; load_dotenv('.env'); print('MySQL password set:', bool(os.getenv('ALADIN_MYSQL_PASSWORD')))"
```

`MySQL password set: True`가 나와야 한다.

환경변수 이름은 다음과 같다.

| 환경변수 | 기본값 | 의미 |
|---|---|---|
| `ALADIN_MYSQL_HOST` | `127.0.0.1` | MySQL 호스트 |
| `ALADIN_MYSQL_PORT` | `3306` | MySQL 포트 |
| `ALADIN_MYSQL_USER` | `root` | MySQL 사용자 |
| `ALADIN_MYSQL_PASSWORD` | 빈 문자열 | MySQL 비밀번호 |
| `ALADIN_MYSQL_DATABASE` | `aladin_manga` | 데이터베이스 이름 |

개발용 PowerShell 세션에서만 임시로 지정하려면 다음과 같이 한다.

```powershell
$env:ALADIN_MYSQL_HOST = "127.0.0.1"
$env:ALADIN_MYSQL_PORT = "3306"
$env:ALADIN_MYSQL_USER = "root"
$env:ALADIN_MYSQL_DATABASE = "aladin_manga"
$env:ALADIN_MYSQL_PASSWORD = "여기에_본인_비밀번호"
```

`.env`를 사용하면 작업 스케줄러가 PowerShell 환경변수를 별도로 전달하지 않아도 된다. 비밀번호를 Python 파일, 배치 파일, Git 저장소에 직접 기록하지 않는다.

작업 스케줄러에서 실행할 때는 다음을 확인한다.

- 예약 작업을 실행하는 Windows 계정이 프로젝트 루트와 `.env`를 읽을 수 있는가?
- MySQL 서비스가 예약 시각 전에 시작되어 있는가?
- MySQL 사용자에게 `aladin_manga` 데이터베이스와 테이블을 생성·수정할 권한이 있는가?

## 4. 최초 데이터 적재

Gold CSV가 이미 생성되어 있다면 프로젝트 루트에서 먼저 입력 파일을 검증한다.

```powershell
python .\mysql_loader.py --dry-run
```

정상이라면 Gold 도서 행과 시리즈 행 개수, 입력 CSV 검증 완료 메시지가 표시된다.

실제 MySQL 적재는 다음과 같이 한다.

```powershell
python .\mysql_loader.py
```

적재기는 실행 과정에서 `mysql_schema.sql`의 테이블을 확인·생성한다. 데이터베이스가 없으면 `aladin_manga` 데이터베이스도 생성한다.

기존 DB가 이전 버전의 `collected_at` 기준 기본키를 사용하고 있으면, 적재기가 `collected_date` 생성 컬럼과 날짜 기준 기본키로 자동 마이그레이션한다. 같은 식별자·같은 날짜의 기존 중복은 가장 최신 `collected_at`만 남긴다.

전체 애플리케이션에는 `mysql_schema.sql`을 사용한다. 이 파일에는 도서·시리즈뿐 아니라 보유목록, 권수 체크, 폴더, 시리즈 순서 테이블까지 포함되어 있다.

## 5. 수동으로 하루치 데이터 실행

### 5.1 전체 파이프라인

프로젝트 루트에서 다음 순서로 실행한다.

```powershell
cd "C:\Users\Playdata\Documents\ChatGPT\개인\aladin_project"

python .\aladin_manga_scraper.py
python .\gold_transform.py
python .\mysql_loader.py
```

각 단계의 결과는 다음과 같다.

| 순서 | 실행 파일 | 결과 |
|---:|---|---|
| 1 | `aladin_manga_scraper.py` | HTML, 최신 CSV, history CSV |
| 2 | `gold_transform.py` | `gold/manga_trend.csv`, `gold/popular_series.csv` |
| 3 | `mysql_loader.py` | MySQL `books`, `book_snapshots`, `series_daily_stats` |

현재 발매일은 목록 HTML 기준으로 월까지만 사용하므로 `release_date_enricher.py`는 일일 파이프라인에 포함하지 않는다.

같은 날 전체 파이프라인을 다시 실행해도 Silver·Gold·MySQL 모두 날짜별 최신 관측으로 교체되므로 동일 날짜의 통계 행이 늘어나지 않는다.

### 5.2 각 단계만 실행하기

크롤링만 하고 결과를 확인하려면:

```powershell
python .\aladin_manga_scraper.py
```

Gold만 다시 계산하려면:

```powershell
python .\gold_transform.py --input .\history\aladin_manga_history.csv
```

MySQL에 적재하지 않고 Gold CSV 형식만 점검하려면:

```powershell
python .\mysql_loader.py --dry-run
```

이미 생성된 Gold CSV를 MySQL에 반영하려면:

```powershell
python .\mysql_loader.py
```

기존 history CSV를 일회성으로 날짜별 최신 행만 남기도록 정리하려면:

```powershell
python .\normalize_history.py
python .\gold_transform.py
python .\mysql_loader.py
```

Gold 변환을 다시 한 뒤에는 반드시 MySQL 적재도 다시 실행해야 Django에서 새 결과를 볼 수 있다.

## 6. 배치 파일을 이용한 전체 실행

프로젝트 루트의 `run_daily_pipeline.bat`은 다음 세 작업을 순서대로 실행한다.

```text
aladin_manga_scraper.py
    ↓
gold_transform.py
    ↓
mysql_loader.py
```

배치 파일은 `%~dp0`를 사용해 자신의 위치를 프로젝트 루트로 인식한다. 따라서 작업 스케줄러가 다른 작업 폴더에서 실행해도 프로젝트 경로를 잃지 않는다. MySQL 설정은 프로젝트 루트 `.env`에서 읽는다.

수동 테스트:

```powershell
cd "C:\Users\Playdata\Documents\ChatGPT\개인\aladin_project"
.\run_daily_pipeline.bat
```

배치 파일은 화면 출력을 로그에 저장하므로 실행 중 PowerShell에 아무것도 표시되지 않을 수 있다. 다른 PowerShell 창에서 실시간 로그를 확인한다.

```powershell
cd "C:\Users\Playdata\Documents\ChatGPT\개인\aladin_project"
Get-Content ".\logs\daily_pipeline.log" -Tail 30 -Wait
```

한국어가 깨져 보이면 UTF-8로 읽는다.

```powershell
Get-Content ".\logs\daily_pipeline.log" -Encoding UTF8 -Tail 30
```

정상적인 단계 흐름은 다음과 같다.

```text
START
CRAWL START
1페이지: ...개 수집
2페이지: ...개 수집
CRAWL DONE
GOLD START
GOLD DONE
MYSQL START
MYSQL DONE
SUCCESS
```

`SUCCESS`는 해당 실행이 끝났다는 뜻이다. 배치 파일은 계속 대기하지 않고 종료되며, 다음 실행은 작업 스케줄러가 다음 예약 시각에 다시 시작한다.

### 6.1 실행 결과 확인

최근 실행 파일의 수정 시각을 확인한다.

```powershell
Get-Item .\aladin_manga.csv, .\gold\manga_trend.csv, .\gold\popular_series.csv, .\history\aladin_manga_history.csv |
    Select-Object Name, Length, LastWriteTime
```

오늘자 원본 HTML 페이지를 확인한다.

```powershell
$runDate = Get-Date -Format "yyyy-MM-dd"
Get-ChildItem ".\raw\$runDate" -File | Select-Object Name, Length, LastWriteTime
```

### 6.2 최근 실행 확인 사례

2026-09-07 실행에서는 다음 흐름이 확인되었다.

- `08:54:46`에 `START`
- 약 21페이지 HTML 수집
- `08:55:56`에 크롤링 완료
- Gold 도서 행 6,717개 생성
- 시리즈 집계 행 3,095개 생성
- MySQL 적재 완료
- `08:55:59`에 `SUCCESS`

따라서 페이지 수와 알라딘 응답 속도에 따라 전체 실행에 약 10분 이상 걸릴 수 있다.

2026-09-04에는 수동 스케줄러 테스트로 같은 날짜가 두 번 들어갔지만, 날짜별 중복 제거 후 9월 4일 최신 관측만 남겼다. 이후 2026-09-07 실행에서도 history·Gold·MySQL에 날짜별 중복이 없는 것을 확인했다.

같은 날 `09:00`에 별도 실행이 시작된 기록이 남을 수 있다. 이처럼 수동 실행을 중간에 중단한 경우에는 `SUCCESS`가 없는 것이 정상이며, 다음 실행 결과를 판단할 때는 시작 시각보다 마지막 단계의 `SUCCESS`를 기준으로 확인한다.

## 7. Windows 작업 스케줄러 설정

### 7.1 작업 만들기

1. Windows 검색창에서 `작업 스케줄러`를 연다.
2. 오른쪽 메뉴에서 `기본 작업 만들기`를 선택한다.
3. 이름을 입력한다.

```text
Aladin Daily Pipeline
```

4. 트리거에서 `매일`을 선택한다.
5. 시작 시간을 현재 설정과 동일하게 `오전 9:00`으로 지정한다.
6. 동작에서 `프로그램 시작`을 선택한다.

### 7.2 프로그램 경로

배치 파일을 실행 대상으로 지정한다.

```text
프로그램/스크립트:
C:\Windows\System32\cmd.exe
```

```text
인수 추가:
/c "C:\Users\Playdata\Documents\ChatGPT\개인\aladin_project\run_daily_pipeline.bat"
```

가능하다면 `시작 위치`에는 다음을 지정한다.

```text
C:\Users\Playdata\Documents\ChatGPT\개인\aladin_project
```

배치 파일이 이미 자신의 위치를 기준으로 동작하므로 시작 위치가 비어 있어도 작동하지만, 명시하는 편이 확인하기 쉽다.

### 7.3 권장 작업 속성

개인 PC에서 처음 설정할 때는 다음 구성이 간단하다.

- `사용자가 로그온한 경우에만 실행`
- `사용자가 요청할 때 작업 실행 허용`
- 예약 시각을 놓치면 가능한 한 빨리 작업 시작
- 작업이 이미 실행 중이면 새 인스턴스를 시작하지 않음

컴퓨터가 절전 상태일 수 있다면 조건 탭에서 예약 시각에 컴퓨터를 깨울지 선택한다. 노트북 배터리 상태에서도 실행하려면 전원 조건을 확인한다.

`사용자가 로그온하지 않아도 실행`을 선택하면 Windows 계정 비밀번호를 요구할 수 있다. 이 경우에도 MySQL 비밀번호와 Windows 계정 비밀번호를 혼동하지 않는다.

### 7.4 테스트

작업 스케줄러에서 생성한 작업을 우클릭하고 `실행`을 눌러 테스트한다. 또는 PowerShell에서 다음처럼 실행한다.

```powershell
Start-ScheduledTask -TaskName "Aladin Daily Pipeline"
Get-ScheduledTaskInfo -TaskName "Aladin Daily Pipeline" |
    Select-Object LastRunTime, LastTaskResult, NextRunTime
```

작업 실행 중에는 `LastTaskResult`가 실행 중 코드로 보일 수 있으므로 완료 후 다시 확인한다.

```powershell
Get-Content ".\logs\daily_pipeline.log" -Encoding UTF8 -Tail 50
```

작업 스케줄러의 `마지막 실행 결과`가 `0x0`이면 성공이다. 실제 로그에 `SUCCESS`가 있는지도 함께 확인한다.

현재 등록된 작업은 매일 오전 9:00으로 설정되어 있다. 오전 8:00 실행을 원하면 작업 스케줄러의 트리거 시간을 별도로 변경해야 한다.

## 8. Django 대시보드 실행

데이터 적재와 Django 서버 실행은 별개의 작업이다. 데이터 수집 배치가 Django 서버를 자동으로 시작하지는 않는다.

PowerShell을 하나 더 열고 다음을 실행한다.

```powershell
cd "C:\Users\Playdata\Documents\ChatGPT\개인\aladin_project\aladin_django\aladin_manga"
..\.venv\Scripts\python.exe manage.py runserver
```

브라우저에서 다음 주소를 연다.

```text
http://127.0.0.1:8000/
```

주요 화면 주소:

| 주소 | 화면 |
|---|---|
| `/` | 오늘의 대시보드 |
| `/search/` | 랭킹 탐색 |
| `/interest-series/` | 관심상품 |
| `/owned-series/` | 마이페이지·보유목록 |

데이터가 새로 적재된 뒤에는 브라우저를 새로고침하면 최신 스냅샷을 조회한다. Django 개발 서버를 매번 재시작할 필요는 없다.

## 9. 장애 대응

### 9.1 `No module named 'mysql'`

현재 활성화된 가상환경에 적재기용 드라이버가 없는 상태다.

```powershell
python -m pip install mysql-connector-python
python -c "import mysql.connector; print('mysql connector OK')"
```

중요한 점은 `pip`만 단독으로 사용하지 말고, 실행에 사용한 동일한 Python으로 `python -m pip`를 실행하는 것이다.

`.env`를 읽는 단계에서 `No module named 'dotenv'`가 나오면 같은 가상환경에 다음 패키지도 설치한다.

```powershell
python -m pip install python-dotenv
python -c "from dotenv import load_dotenv; print('python-dotenv OK')"
```

가상환경을 활성화하지 않은 상태라면 프로젝트의 `.venv\Scripts\python.exe`를 직접 사용한다.

### 9.2 로그 파일이 없음

실제 파일명에 밑줄 앞의 백슬래시가 들어가지 않았는지 확인한다.

```powershell
Test-Path .\run_daily_pipeline.bat
Test-Path .\logs\daily_pipeline.log
```

정상 경로:

```text
.\logs\daily_pipeline.log
```

잘못된 예:

```text
.\logs\daily\_pipeline.log
```

배치 파일이 프로젝트 루트에 있는지도 확인한다.

```powershell
Get-Item .\run_daily_pipeline.bat
```

### 9.3 `CRAWL START` 이후 로그가 없음

이 단계에서는 아직 Gold 변환과 MySQL 적재가 시작되지 않았다. 크롤러가 알라딘 첫 HTTP 요청을 기다리거나, 응답을 파싱하는 중일 수 있다.

확인 순서:

1. `raw\YYYY-MM-DD` 폴더에 오늘자 HTML 파일이 생성됐는지 확인한다.
2. 작업 스케줄러의 작업 상태가 `실행 중`인지 확인한다.
3. 알라딘 페이지를 일반 브라우저에서 열 수 있는지 확인한다.
4. 배치 파일을 수동으로 실행해 같은 문제가 발생하는지 확인한다.
5. 10~15분 이상 진행이 없으면 작업을 종료하고 로그의 마지막 상태를 확인한다.

현재 배치 파일은 Python `-u` 옵션을 사용하므로, 다음 실행부터 페이지별 출력이 로그에 즉시 기록된다. 단, HTTP 요청이 첫 응답을 기다리는 동안에는 첫 페이지 메시지가 나오기 전까지 잠시 정지해 보일 수 있다.

같은 날짜에 배치를 다시 실행해도 정상이다. 크롤러·Gold·MySQL 적재 단계가 모두 `item_id + KST 날짜` 기준으로 최신 관측을 유지하므로 같은 날짜의 통계 행이 계속 늘어나지 않는다. 기존 history에 중복이 이미 쌓인 경우에는 다음 일회성 정리 명령을 실행한다.

```powershell
python .\normalize_history.py
python .\gold_transform.py
python .\mysql_loader.py
```

### 9.4 `FAILED`가 기록됨

`FAILED` 바로 앞의 로그를 확인한다.

```powershell
Get-Content .\logs\daily_pipeline.log -Encoding UTF8 -Tail 100
```

실패한 단계에 따라 대응한다.

| 마지막 단계 | 우선 확인할 것 |
|---|---|
| `CRAWL START` | 인터넷, 알라딘 접근, 오늘자 raw 폴더 |
| `GOLD START` | history CSV 인코딩·필수 컬럼·수집 시각 |
| `MYSQL START` | MySQL 서비스, 환경변수, 커넥터 설치, 계정 권한 |

### 9.5 MySQL 연결 오류

다음 항목을 확인한다.

- MySQL 서비스가 실행 중인가?
- 프로젝트 루트 `.env`가 존재하는가?
- `.env`의 호스트·포트·사용자·비밀번호가 맞는가?
- `ALADIN_MYSQL_DATABASE` 값이 영문·숫자·밑줄로 되어 있는가?
- 해당 사용자가 데이터베이스와 테이블을 생성할 권한이 있는가?

비밀번호 자체를 출력하지 않고 `.env` 로딩 여부만 확인한다.

```powershell
python -c "from dotenv import load_dotenv; import os; load_dotenv('.env'); print('MySQL password set:', bool(os.getenv('ALADIN_MYSQL_PASSWORD'))); print('Database:', os.getenv('ALADIN_MYSQL_DATABASE'))"
```

`MySQL password set: True`가 나오고 데이터베이스명이 `aladin_manga`인지 확인한다. 배치 실행에서는 PowerShell에 임시로 설정한 환경변수보다 프로젝트 루트 `.env`와 작업 스케줄러 실행 계정의 파일 읽기 권한을 우선 확인한다.

CSV 입력만 점검하는 `--dry-run`은 MySQL 연결을 테스트하지 않는다. 실제 연결은 다음 명령으로 확인한다.

```powershell
python .\mysql_loader.py
```

### 9.6 대시보드에 오늘 데이터가 안 보임

1. `mysql_loader.py` 로그에 `MYSQL DONE`, `SUCCESS`가 있는지 확인한다.
2. Django 서버가 올바른 MySQL 환경변수를 사용하고 있는지 확인한다.
3. 브라우저를 새로고침한다.
4. 검색 화면의 수집 스냅샷 선택 목록에서 최신 시각을 선택한다.
5. MySQL의 `book_snapshots`에 최신 `collected_at`이 들어갔는지 확인한다.

## 10. 데이터 보존과 백업

분석 재현에 중요한 파일은 다음과 같다.

- `raw/`: 원본 HTML
- `history/aladin_manga_history.csv`: 누적 수집 이력
- `gold/manga_trend.csv`: 도서 추이 결과
- `gold/popular_series.csv`: 시리즈 집계 결과
- `.env`: MySQL 접속 설정과 비밀번호
- MySQL 사용자 보유목록 테이블

최소한 `raw`, `history`, `gold` 폴더는 주기적으로 백업한다. MySQL의 보유목록까지 백업하려면 별도 `mysqldump`를 사용한다.

```powershell
& "C:\Program Files\MySQL\MySQL Server 8.0\bin\mysqldump.exe" -h 127.0.0.1 -P 3306 -u root -p --databases aladin_manga --result-file=".\backup\aladin_manga_backup.sql"
```

비밀번호는 명령어에 직접 쓰지 않고 실행 후 입력한다. 백업 파일에도 개인정보나 보유목록 정보가 포함될 수 있으므로 외부 공개 저장소에 올리지 않는다.

`mysqldump`가 명령으로 인식되지 않으면 MySQL 실행 파일이 PATH에 등록되지 않은 상태다. 현재 설치 경로에서는 다음처럼 전체 경로와 `--result-file` 옵션을 사용한다.

```powershell
New-Item -ItemType Directory -Force .\backup | Out-Null
& "C:\Program Files\MySQL\MySQL Server 8.0\bin\mysqldump.exe" -h 127.0.0.1 -P 3306 -u root -p --databases aladin_manga --result-file=".\backup\aladin_manga_backup.sql"
```

생성 여부는 다음으로 확인한다.

```powershell
Get-Item .\backup\aladin_manga_backup.sql | Select-Object Name, Length
```

## 11. 일일 운영 체크리스트

### 자동 실행 전

- [ ] MySQL 서비스 실행
- [ ] PC가 켜져 있거나 예약 작업이 절전에서 깨어나도록 설정
- [ ] 작업 스케줄러 트리거가 오전 9시인지 확인
- [ ] `mysql-connector-python` 설치 확인
- [ ] 프로젝트 루트 `.env` 존재 및 비밀번호 설정 확인

### 실행 후

- [ ] 로그에 오늘 날짜의 `START` 확인
- [ ] 오늘자 raw HTML 페이지 생성 확인
- [ ] `CRAWL DONE` 확인
- [ ] `GOLD DONE` 확인
- [ ] `MYSQL DONE` 확인
- [ ] 마지막에 `SUCCESS` 확인
- [ ] 대시보드 최신 스냅샷 확인

## 12. 현재 실행하지 않는 기능

다음 기능은 현재 일일 배치에 포함하지 않는다.

### `release_date_enricher.py`

상품 상세 페이지를 추가 요청해 발매일을 일자까지 보강하는 도구다. 현재 화면 요구사항이 연·월 표시이므로 매일 실행하지 않는다.

### 전체 만화 카탈로그 수집

현재 크롤러는 알라딘 만화 베스트셀러 페이지를 수집한다. 순위에 한 번도 들어오지 않은 모든 만화책을 검색하는 전체 카탈로그 수집은 별도 기능이다.

## 13. 날짜별 중복 정리

일반적인 일일 실행에서는 같은 날짜에 하나의 최신 통계만 유지된다. 수동 재실행이나 과거 버전으로 인해 history CSV에 같은 날짜의 중복이 생긴 경우에만 다음 순서로 정리한다.

```powershell
python .\normalize_history.py
python .\gold_transform.py
python .\mysql_loader.py
```

`normalize_history.py`는 기존 history CSV를 백업한 뒤, 같은 상품·같은 KST 날짜에서 `collected_at`이 가장 최신인 행만 남긴다. 이후 Gold와 MySQL을 다시 생성·적재해야 대시보드에도 정리 결과가 반영된다. MySQL 적재기는 기존 테이블에 날짜 키가 없는 경우에도 `collected_date`를 추가하고 오래된 중복을 제거하는 마이그레이션을 수행한다.

## 14. GitHub 업로드 전 점검 및 업로드

### 14.1 먼저 백업하기

GitHub는 MySQL 데이터를 백업하지 않는다. 업로드 전에 순위 통계·보유목록이 들어 있는 MySQL 전체 데이터베이스와 다음 Gold 실행에 필요한 history CSV를 별도로 보관한다.

프로젝트 루트에서 실행한다.

```powershell
New-Item -ItemType Directory -Force .\backup | Out-Null
& "C:\Program Files\MySQL\MySQL Server 8.0\bin\mysqldump.exe" -h 127.0.0.1 -P 3306 -u root -p --databases aladin_manga --result-file=".\backup\aladin_manga_2026-09-07.sql"
Copy-Item .\history\aladin_manga_history.csv .\backup\aladin_manga_history_2026-09-07.csv
```

`mysqldump`가 비밀번호를 물어보면 입력한다. 백업 파일에는 보유목록과 통계가 포함될 수 있으므로 GitHub에 올리지 않는다. 프로젝트의 `.gitignore`에는 이미 다음 제외 항목이 포함되어 있다.

```gitignore
raw/
logs/
*.log
backup/
```

### 14.2 업로드 직전 확인

현재 상위 `개인` 폴더에도 Git 저장소가 있으므로 반드시 프로젝트 폴더 안에서 작업한다.

```powershell
cd "C:\Users\Playdata\Documents\ChatGPT\개인\aladin_project"
git rev-parse --show-toplevel
```

결과가 `aladin_project` 경로인지 확인한다. GitHub 저장소의 첫 화면에 보고서를 표시하려면 VS Code 탐색기에서 `README.md.md`를 `README.md`로 변경하는 것을 권장한다.

업로드하지 않을 파일이 제외되는지 확인한다.

```powershell
git check-ignore -v .env .\aladin_django\.venv .\raw .\logs .\backup
```

목록에 실제 비밀번호, `.env`, `.venv`, `raw`, `logs`, `backup` 파일이 포함되지 않는지 반드시 확인한다. `.env.example`, `history`, `gold`, SQL 스키마와 소스 코드는 업로드 대상이다.

### 14.3 GitHub 저장소 생성과 첫 업로드

GitHub에서 새 저장소를 만들 때는 `README`, `.gitignore`, `License`를 자동 생성하지 않는 빈 저장소로 만든다. 프로젝트 폴더에서 다음을 실행한다.

```powershell
git init
git branch -M main
git add .
git status --short
git diff --cached --name-only
git commit -m "Initial commit: Aladin manga dashboard"
git remote add origin https://github.com/사용자명/aladin-manga-pulse.git
git push -u origin main
```

`git diff --cached --name-only` 결과에 `.env`, `.venv`, `raw`, `logs`, `backup`이 보이면 커밋을 중단하고 `.gitignore`를 먼저 수정한다. GitHub HTTPS 인증은 GitHub 로그인 또는 Personal Access Token을 사용한다.

## 15. 다른 컴퓨터·집에서 실행하기

### 15.1 프로젝트 내려받기

집 컴퓨터에서 원하는 폴더로 이동한 후 GitHub 저장소를 내려받는다. 아래 경로는 예시이므로 집 컴퓨터에 맞게 바꾼다.

```powershell
cd "D:\Projects"
git clone https://github.com/사용자명/aladin-manga-pulse.git
cd .\aladin-manga-pulse
```

### 15.2 가상환경과 패키지 준비

```powershell
python -m venv .\aladin_django\.venv
.\aladin_django\.venv\Scripts\Activate.ps1
python -m pip install -r .\aladin_django\requirements.txt
```

`mysql_loader.py` 또는 `.env` 로딩에서 모듈 오류가 나오면 같은 가상환경에 추가 설치한다.

```powershell
python -m pip install mysql-connector-python python-dotenv
```

### 15.3 집 컴퓨터의 MySQL 연결 설정

`.env`는 GitHub에 올라가지 않으므로 새 컴퓨터에서 다시 만든다.

```powershell
Copy-Item .env.example .env
notepad .env
```

집 컴퓨터에서 MySQL도 로컬로 실행한다면 `ALADIN_MYSQL_HOST=127.0.0.1`로 설정한다. 이때 `127.0.0.1`은 집 컴퓨터를 뜻한다. 다른 컴퓨터의 MySQL을 사용한다면 해당 컴퓨터의 IP 주소로 바꾼다.

### 15.4 기존 데이터 복원

기존 순위·보유목록을 이어서 사용하려면 MySQL 서비스를 먼저 실행하고 백업 SQL을 복원한다.

```powershell
cmd /c '"C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe" -h 127.0.0.1 -P 3306 -u root -p < "C:\Backup\aladin_manga_2026-09-07.sql"'
```

다음 Gold 실행에서 과거 순위와 비교하려면 history CSV도 복사한다.

```powershell
Copy-Item "C:\Backup\aladin_manga_history_2026-09-07.csv" .\history\aladin_manga_history.csv
```

MySQL 백업을 복원했다면 대시보드의 기존 통계는 바로 사용할 수 있다. history만 복원했거나 기존 데이터를 새로 적재하려는 경우에는 다음을 실행한다.

```powershell
python .\gold_transform.py
python .\mysql_loader.py
```

`raw`와 `logs`는 복원하지 않아도 된다. 새로 크롤링하거나 Django를 실행하면 필요한 폴더와 로그가 다시 생성된다.

### 15.5 Django 접속 주소

집 컴퓨터에서 Django를 실행하면 브라우저 주소는 다음과 같다.

```powershell
cd .\aladin_django\aladin_manga
..\.venv\Scripts\python.exe manage.py runserver
```

```text
http://127.0.0.1:8000/
```

`127.0.0.1`은 현재 서버를 실행한 컴퓨터 자신이므로, 집 컴퓨터에서 실행하면 집 컴퓨터의 브라우저에서 접속할 수 있다. 휴대폰이나 다른 PC에서 접속하려면 다음처럼 실행한 뒤 집 컴퓨터의 IPv4 주소를 사용한다.

```powershell
..\.venv\Scripts\python.exe manage.py runserver 0.0.0.0:8000
ipconfig
```

예: `http://192.168.0.10:8000/`. 이 경우 Windows 방화벽의 사설 네트워크 허용이 필요하며, 인터넷 전체에 공개하려면 별도의 운영 배포 설정이 필요하다.

### 15.6 작업 스케줄러 재등록

작업 스케줄러 작업은 GitHub에 저장되지 않는다. 집 컴퓨터에서 `Aladin Daily Pipeline` 작업을 새로 만들고, 집의 실제 프로젝트 경로를 사용해 `run_daily_pipeline.bat`을 연결한다.

```text
프로그램/스크립트:
C:\Windows\System32\cmd.exe

인수 추가:
/c "D:\Projects\aladin-manga-pulse\run_daily_pipeline.bat"
```

배치 파일은 자신의 위치를 기준으로 Python과 로그 경로를 찾으므로 코드 안의 경로를 수정할 필요는 없다. 단, 작업 스케줄러의 대상 경로와 시작 위치는 새 컴퓨터에 맞게 지정해야 한다.

## 16. 권장 실행 순서 요약

### 최초 설정

```powershell
cd "C:\Users\Playdata\Documents\ChatGPT\개인\aladin_project\aladin_django"
.\.venv\Scripts\Activate.ps1
cd ..
python -m pip install -r .\aladin_django\requirements.txt
python .\mysql_loader.py --dry-run
python .\mysql_loader.py
```

기존 history에 날짜별 중복이 확인된 경우에만 다음 정리 명령을 먼저 실행한다.

```powershell
python .\normalize_history.py
python .\gold_transform.py
python .\mysql_loader.py
```

### 하루치 수동 실행

```powershell
cd "C:\Users\Playdata\Documents\ChatGPT\개인\aladin_project"
.\run_daily_pipeline.bat
```

### 대시보드 실행

별도 PowerShell에서:

```powershell
cd "C:\Users\Playdata\Documents\ChatGPT\개인\aladin_project\aladin_django\aladin_manga"
..\.venv\Scripts\python.exe manage.py runserver
```

### 자동 실행

Windows 작업 스케줄러에서 `run_daily_pipeline.bat`을 매일 오전 9시에 실행하도록 등록한다. 현재 등록된 작업 이름은 `Aladin Daily Pipeline`이다.
