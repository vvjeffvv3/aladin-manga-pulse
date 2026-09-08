# 알라딘 만화 프로젝트 테스트 가이드

## 1. 문서 목적

이 문서는 알라딘 만화 프로젝트의 테스트 구조와 실행 방법을 설명한다. 기능을 추가할 때 어느 계층에 테스트를 작성해야 하는지, 테스트용 DB와 운영 DB가 어떻게 분리되는지도 함께 정리한다.

현재 테스트는 다음 두 명령으로 실행한다.

- 루트 파이프라인 테스트 19개
- Django 테스트 44개
- 전체 합계 63개

## 2. 테스트 디렉터리 구조

```text
aladin_project/
├─ tests/
│  ├─ __init__.py
│  ├─ test_scraper.py
│  ├─ test_daily_snapshot.py
│  ├─ test_gold_transform.py
│  ├─ test_mysql_loader.py
│  └─ test_daily_pipeline.py
│
└─ aladin_django/
   └─ aladin_manga/
      └─ dashboard/
         └─ tests/
            ├─ __init__.py
            ├─ runner.py
            ├─ test_formatting.py
            ├─ test_dashboard_service.py
            ├─ test_search_service.py
            ├─ test_owned_series_service.py
            ├─ test_views.py
            └─ test_repositories.py
```

## 3. 테스트 계층

| 계층 | 테스트 파일 | 방식 | 확인 대상 |
|---|---|---|---|
| 크롤러 | `tests/test_scraper.py` | `unittest`, 샘플 HTML | 제목·작가·가격·평점·판매지수 추출, 재시도 |
| 날짜 스냅샷 | `tests/test_daily_snapshot.py` | `unittest` | 같은 날짜 중복 제거, 최신 행 선택 |
| Gold 변환 | `tests/test_gold_transform.py` | `unittest` | 순위 변화·신규·이탈·시리즈 집계 |
| Loader | `tests/test_mysql_loader.py` | 임시 CSV·가짜 커넥터 | CSV 검증, 적재 파라미터, 커밋·롤백 |
| 일일 배치 | `tests/test_daily_pipeline.py` | 배치 계약 검사 | 크롤링→Gold→MySQL 순서, 로그·실패 처리 |
| Service | `dashboard/tests/test_*_service.py` | `SimpleTestCase`, Mock | 화면용 계산과 상태 조합 |
| View | `dashboard/tests/test_views.py` | `SimpleTestCase`, Django Client | URL, 템플릿, POST, 메시지, JSON 응답 |
| Repository | `dashboard/tests/test_repositories.py` | `TransactionTestCase`, 테스트 DB | 실제 ORM 검색·저장·정렬 |

## 4. 사전 준비

프로젝트 루트에서 가상환경을 활성화하고 의존성을 설치한다.

```powershell
cd "C:\Users\Playdata\Documents\ChatGPT\개인\aladin_project"
.\aladin_django\.venv\Scripts\Activate.ps1
python -m pip install -r .\aladin_django\requirements.txt
```

Django Repository 테스트는 MySQL 테스트 DB를 만들기 때문에 다음 조건이 필요하다.

- `.env`의 MySQL 접속 정보가 정상이어야 한다.
- MySQL 계정에 테스트 DB 생성 권한이 있어야 한다.
- `mysqlclient`가 설치되어 있어야 한다.

## 5. 루트 파이프라인 테스트 실행

프로젝트 루트에서 실행한다.

```powershell
cd "C:\Users\Playdata\Documents\ChatGPT\개인\aladin_project"
python -m unittest discover -s . -p "test_*.py" -v
```

가상환경을 활성화하지 않고 실행하려면 프로젝트의 Python 실행 파일을 직접 지정한다.

```powershell
.\aladin_django\.venv\Scripts\python.exe -m unittest discover -s . -p "test_*.py" -v
```

이 명령은 다음을 검증한다.

- 샘플 HTML에서 필요한 만화 정보 추출
- 네트워크 오류·알라딘 오류 페이지 발생 시 최대 3회 재시도
- 같은 상품의 날짜별 최신 관측 유지
- Gold 순위 변화·신규·이탈 계산
- Loader 입력 CSV 검증·중복 제거·시간·숫자 변환
- Loader 예외 발생 시 롤백·커서·연결 종료
- 배치 파일의 실행 순서와 로그·종료 상태

Loader 테스트는 실제 MySQL에 접속하지 않는다. `FakeConnection`과 `FakeCursor`가 실행 SQL과 파라미터, 커밋·롤백 호출을 기록한다. 배치 테스트도 실제 크롤링을 실행하지 않고 `run_daily_pipeline.bat`의 단계 순서와 오류 처리 계약을 확인한다.

## 6. Django 테스트 실행

`manage.py`가 있는 디렉터리에서 실행한다.

```powershell
cd "C:\Users\Playdata\Documents\ChatGPT\개인\aladin_project\aladin_django\aladin_manga"
python manage.py test dashboard -v 2
```

가상환경을 활성화하지 않았다면 다음처럼 실행한다.

```powershell
..\.venv\Scripts\python.exe manage.py test dashboard -v 2
```

### 6.1 Service·View 테스트

Service와 View 테스트는 `SimpleTestCase`와 Mock을 사용한다.

- 실제 보유목록·관심상품 데이터에 접근하지 않는다.
- Service의 반환값을 가짜로 만들고 계산·분기만 확인한다.
- View는 Django Client로 GET·POST 요청을 보내고 템플릿·메시지·리다이렉트를 확인한다.
- 네트워크나 운영 MySQL이 필요하지 않다.

### 6.2 Repository 테스트

Repository 테스트는 `TransactionTestCase`를 사용해 실제 Django ORM 쿼리를 실행한다.

1. Django가 별도의 테스트 DB를 만든다. 일반적으로 이름은 `test_aladin_manga`다.
2. 모델이 `managed=False`이므로 테스트 시작 시 Repository에 필요한 테이블을 직접 생성한다.
3. 스냅샷·도서·시리즈·보유목록·폴더 데이터를 테스트 DB에 넣고 조회·저장 결과를 확인한다.
4. 테스트 종료 시 테이블과 테스트 DB를 정리한다.

따라서 운영 DB `aladin_manga`의 데이터는 변경되지 않는다. 테스트 DB 생성 권한이 없으면 Service·View 테스트는 실행할 수 있지만 Repository 테스트에서 오류가 발생한다.

## 7. 현재 테스트 파일별 범위

### 7.1 루트 테스트: 19개

| 파일 | 테스트 수 | 주요 검증 |
|---|---:|---|
| `test_scraper.py` | 6 | 파싱, 작가 추출, 제목 분리, 재시도 |
| `test_daily_snapshot.py` | 4 | 날짜별 중복 제거, 누락값 거부 |
| `test_gold_transform.py` | 2 | Gold 변화 계산, 인기 시리즈 집계 |
| `test_daily_pipeline.py` | 2 | 배치 실행 순서, 로그·실패 계약 |
| `test_mysql_loader.py` | 5 | CSV·적재·커밋·롤백 |

### 7.2 Django 테스트: 44개

| 파일 | 테스트 수 | 주요 검증 |
|---|---:|---|
| `test_formatting.py` | 4 | 발매일 화면 표시 |
| `test_dashboard_service.py` | 3 | 홈 대시보드와 순위 상태 |
| `test_search_service.py` | 3 | 검색·페이지네이션·최신 권수 |
| `test_owned_series_service.py` | 10 | 보유 권수·수집률·폴더 |
| `test_views.py` | 15 | 화면 요청·POST·JSON API |
| `test_repositories.py` | 9 | 실제 ORM 조회·저장·정렬 |

## 8. 테스트 출력 형식

커스텀 테스트 결과 출력기가 테스트 메서드의 docstring을 설명으로 사용한다.

```text
=========test_views.py====================
검색 화면에 가격 정렬 선택지를 표시 : 테스트 통과

=========test_repositories.py====================
도서 검색이 가격 기준 오름차순·내림차순을 모두 지원 : 테스트 통과

==================================
[통과] 전체 테스트 통과: 44개 테스트를 모두 통과했습니다.
```

루트 테스트도 같은 형식으로 표시된다.

```text
=========test_mysql_loader.py====================
전체 Loader가 CSV 중복 제거 후 테이블·마이그레이션·적재 순서로 커밋 : 테스트 통과

==================================
[통과] 전체 테스트 통과: 19개 테스트를 모두 통과했습니다.
```

## 9. 새 기능에 테스트 추가하는 방법

새 기능은 다음 순서로 추가한다.

1. 기능의 정상 동작과 실패 조건을 문장으로 정한다.
2. 기능이 속한 계층을 선택한다.
3. 정상 입력, 잘못된 입력, 빈 데이터 또는 경계값 테스트를 작성한다.
4. 기능 로직을 구현한다.
5. 해당 테스트를 먼저 실행한다.
6. 루트 테스트와 Django 테스트를 모두 실행한다.

계층 선택 기준은 다음과 같다.

- HTML 선택자나 크롤링 재시도 변경 → `tests/test_scraper.py`
- 날짜 중복 제거 변경 → `tests/test_daily_snapshot.py`
- 순위·시리즈 계산 변경 → `tests/test_gold_transform.py`
- CSV 적재·트랜잭션 변경 → `tests/test_mysql_loader.py`
- 화면용 계산 변경 → `dashboard/tests/test_*_service.py`
- URL·템플릿·POST 응답 변경 → `dashboard/tests/test_views.py`
- ORM 조회·저장 변경 → `dashboard/tests/test_repositories.py`

예를 들어 가격 정렬을 추가할 때는 다음 세 곳을 함께 확인한다.

1. `book_repository.py`에 가격 정렬 필드 추가
2. `search.html`에 가격 선택지 추가
3. Repository 테스트에 가격 오름차순·내림차순 테스트 추가

화면에 선택지가 실제로 나타나는지는 View 테스트에서 별도로 확인한다.

## 10. 테스트 작성 규칙

- 파일명은 `test_*.py`로 시작한다.
- 테스트 메서드는 `test_`로 시작한다.
- 테스트 메서드 첫 줄에 한국어 docstring으로 검증 내용을 작성한다.
- 외부 네트워크 호출은 기본 테스트에서 하지 않는다.
- Service·View 테스트는 Mock으로 외부 계층을 격리한다.
- Repository 테스트는 운영 DB가 아닌 Django 테스트 DB에서만 실행한다.
- 테스트 하나가 다른 테스트의 데이터에 의존하지 않도록 매 테스트 전 데이터를 정리한다.
- 기능 구현 후 해당 테스트와 전체 테스트를 모두 실행한다.

## 11. 실패 대응

### `No module named 'django'`

가상환경이 활성화되었는지 확인하고 Django 의존성을 설치한다.

```powershell
cd "C:\Users\Playdata\Documents\ChatGPT\개인\aladin_project"
.\aladin_django\.venv\Scripts\Activate.ps1
python -m pip install -r .\aladin_django\requirements.txt
```

### Repository 테스트에서 테스트 DB 생성 권한 오류

`.env`의 접속 정보가 운영 DB를 가리키는 것은 정상이다. Django가 별도로 `test_aladin_manga`를 만들기 때문에 MySQL 계정에 테스트 DB 생성 권한이 필요하다. 권한을 확인하고 테스트를 다시 실행한다.

### 테스트 실행 중 한국어가 깨져 보임

테스트의 성공 여부는 마지막의 `OK`와 `[통과]`를 기준으로 확인한다. Windows 터미널 인코딩을 UTF-8로 바꾸면 한글 설명을 정상적으로 볼 수 있다.

```powershell
chcp 65001
```

### 테스트가 중간에 중단됨

Django 테스트가 강제 종료되면 테스트 DB가 남을 수 있다. 다음 실행에서 같은 테스트 DB 이름 충돌이 발생하면 Django가 안내하는 삭제 여부를 확인하고, 운영 DB 이름인 `aladin_manga`와 혼동하지 않도록 한다.

## 12. 현재 테스트의 한계

- 실제 알라딘 사이트의 HTML 변경을 자동으로 검증하지 않는다.
- Loader 테스트는 가짜 MySQL 커넥터를 사용하므로 실제 mysql-connector-python 네트워크 연결 자체를 검증하지 않는다.
- 배치 테스트는 실제 `.bat` 실행 대신 명령 순서와 로그 계약을 검증한다.
- 실제 크롤링부터 MySQL 적재까지의 전체 실환경 검증은 별도로 수동 실행해야 한다.
