# Version 4.3.1 프로젝트 정리 보고서

## 이전 구조와 새 구조

이전에는 `app.py` 약 770줄과 운영 모듈·테스트·실제 API 확인 스크립트가 최상위 폴더에 함께 있었습니다. 테마는 `.streamlit/config.toml`, 번역은 `translations/`, 개인 데이터는 `data/`에 있었습니다.

현재 `app.py`는 `components.dashboard.main()`을 실행하는 **5줄의 진입점**입니다. 자동 페이지 탐색용 `pages/`는 만들지 않았으며 기존 사용자 정의 메뉴를 유지합니다.

| 위치 | 역할 및 이동한 파일 |
|---|---|
| `analytics/` | `pitching.py`, `advanced_hitting.py`, `advanced_pitching.py`, `advanced_stats.py`, `advanced_stats_sources.py`; 기존 기본 지표 상수·숫자 변환을 분리한 `standard.py` |
| `services/` | `ai_analyst.py`, `league_stats.py`, `player_detection.py`, `player_search.py`, `season_selection.py`; app의 요청·응답 검증을 분리한 `player_stats.py` |
| `components/` | `advanced_stats_ui.py`, `ai_ui.py`, `awards.py`, `league_ui.py`, `profile_ui.py`, `ui_components.py`, `ui_styles.css`; 기존 화면 조립 코드 `dashboard.py`와 분리한 `stat_charts.py` |
| `utils/` | `favorites.py`, `i18n.py`; 파일 이동에 영향받지 않는 프로젝트 경로 `paths.py` |
| `tests/` | 기존 `test_*.py` 전체와 `advanced-verified-examples.json`; 새 구조 검증 `test_structure.py` |
| `scripts/` | 기존 `check_*.py` 전체; 실행기 검증 `check_launcher.py`, 읽기 전용 실서비스 확인 `check_connections.py` |
| `docs/` | 이전 README를 `V42_README.ko.md`로 보존, `V43_REPORT.ko.md` 이동, 이 보고서 |
| 최상위 | `app.py`, 새 `README.md`, `start.bat`, 의존성 파일, `.gitignore`; 승인 대기 중인 기존 생성 자료 보존 |

각 Python 폴더의 `__init__.py`는 패키지와 unittest 검색을 위한 파일입니다. 계층만 늘리는 빈 기능 모듈이나 호환용 중복 소스는 만들지 않았습니다. 기존의 수상·리그 등 일부 모듈이 가진 세부 역할은 그대로 유지하며, 이번에는 특히 큰 진입점의 API·차트·화면 조립 책임을 분리했습니다.

## 수정 내용

- 모든 import, 테스트 mock 경로, 임베디드 AppTest 스크립트와 subprocess import를 새 패키지 경로에 맞췄습니다.
- AppTest의 진입점은 최상위 `app.py`의 절대 경로를 사용합니다. 실행 후 캐시되는 화면 모듈의 함수가 실제 사용되는 위치를 mock하도록 조정했습니다.
- CSS는 화면 모듈 옆에서 찾고, 번역과 개인 데이터 기본 폴더는 `utils.paths.PROJECT_ROOT`로 찾습니다. `MLB_ANALYTICS_DATA_DIR` 지원은 유지합니다.
- 분리 후 화면 모듈에 남은 사용하지 않는 API·차트 import를 제거했습니다. 계산 함수의 이름이 비슷하다는 이유로 공식을 통합하거나 변경하지 않았습니다.
- `.gitignore`에 Python 캐시, 테스트 캐시, 로그, 임시 파일, 환경변수 파일, Streamlit 비밀 설정과 로컬 PowerShell 캐시 폴더를 추가했습니다. 기존 가상환경·사용자 데이터·백업 제외 규칙을 유지합니다.
- README에 설치, 환경 설정, Ollama, 실행기, 수동 실행, 테스트, 확장 방법과 알려진 제한을 정리했습니다. 검증 도구는 프로젝트 최상위에서 `python -m scripts.도구이름`으로 실행합니다.
- `start.bat`, 요구 패키지, 테마 설정, 번역 내용, 통계 상수, UI 디자인과 메뉴는 변경하지 않았습니다.

## 삭제 후보: 아직 삭제하지 않음

| 대상 | 정리 후보인 이유 | 현재 처리 |
|---|---|---|
| 최상위의 기존 `*-results.log`, `test-results.log` | 과거 테스트·브라우저·AI 실행 출력이며 앱 실행에 필요하지 않음 | 모두 보존 |
| `v43-source-inventory.json` | 4.3 작업 당시의 경로 목록으로 현재 경로와 다름 | 보존 |
| `ui-preview/` | 과거 브라우저 검증 이미지; 실행에 불필요하지만 디자인 비교에 유용할 수 있음 | 보존 |
| `Microsoft/Windows/PowerShell/ModuleAnalysisCache` | 프로젝트 Python 소스가 아닌 PowerShell 생성 캐시 | 보존 및 Git 제외 |
| `__pycache__/` | 다시 생성 가능한 Python 바이트코드 | 삭제하지 않고 Git 제외 |
| `.venv/` | 기존 Python 경로가 깨져 있지만 의존성 기록이나 환경 복원에 쓰일 수 있음 | 보존; 실행기는 기존 fallback 유지 |
| 오래된 `.backups/` 항목 | 이전 버전 복구용이지만 시간이 지나면 공간 정리 대상일 수 있음 | 전부 보존 |

`scripts/check_browser.py`, `check_ui_browser.py`, `check_v42_browser.py`는 서로 다른 시점의 브라우저 검증 범위를 가지므로 중복 파일로 단정하지 않았습니다. 이전 화면 선택자는 재검증이 필요할 수 있지만 도구는 보존했습니다. 동명의 중복 운영 소스를 새로 남기지 않았습니다.

삭제는 수행하지 않았습니다. 위 비일상 파일을 삭제하려면 사용자의 별도 승인이 필요합니다.

## 검증 결과

| 검증 | 결과 |
|---|---|
| `python -m unittest discover -v` | **144개 통과, 실패 0개** (`v431-test-results.log`) |
| 기존 142개 회귀 테스트 | 검색·팀 필터·즐겨찾기·시즌·타자/투수/겸업·기본/고급 통계·리그·비교·수상·언어·AI 테스트 유지 |
| 새 구조 테스트 2개 | 프로젝트 외부 작업 디렉터리에서도 경로·번역 확인, 운영 패키지 import 그래프의 순환 없음 |
| 주요 메뉴 렌더링 | Streamlit AppTest로 대시보드·선수 기록·비교·수상·AI 화면 및 상태 유지 통과 |
| `python -m scripts.check_startup` | Streamlit 서버 시작 및 health 응답 확인 통과 |
| `python -m scripts.check_launcher` | 실제 Windows `start.bat`을 임시 포트·임시 데이터 폴더로 실행하고 health 응답·생성 프로세스 종료 확인 통과 |
| `python -m scripts.check_connections` | 2024년 MLB ID 660271 타격·543037 투구의 정규시즌 조회 통과; 실제 로컬 Ollama 연결과 모델 목록 1개 확인 |
| Ollama 실패 처리 | mock 기반 연결 실패·시간 초과·선택 기능 및 재시도 회귀 테스트 통과 |
| 즐겨찾기·설정 보존 | 작업 전후 기존 두 파일의 SHA-256 해시 동일 |
| 계산·추출 로직 비교 | 기존 계산/출처 모듈 6개 및 추출한 API·차트 함수의 AST가 import 경로 변경 외에 동일함을 확인 |

실행기 검증 중 샌드박스가 테스트 프로세스 종료를 막아 해당 테스트가 한 번 실패했습니다. 이후 허용된 환경에서 검증용 프로세스만 정리하고 충돌 없는 임시 포트로 다시 실행해 통과했습니다. 실제 연결 확인 로그를 PowerShell에서 리다이렉션한 실행은 경고 출력 때문에 종료 상태가 오류로 표시되어, 리다이렉션 없이 다시 실행했고 **종료 코드 0**을 확인했습니다.

이번에 실제 AI 문장 생성이나 Playwright를 통한 전체 브라우저 시각 회귀 검증은 실행하지 않았습니다. AI는 실제 연결·모델 목록 및 mock 기반 동작까지 검증했고, 화면은 AppTest와 서버/실행기 시작 검증 범위입니다. 4.3의 통계 제한과 로컬 모델 해석 오류 가능성은 그대로 남습니다.

## 백업과 복원

작업 시작 시 `.git` 폴더와 실행 가능한 Git 명령을 찾지 못했습니다. 대신 `.backups/pre-v431-20261104-162510/`에 기존 최상위 파일과 `translations/`, `.streamlit/`을 복사했습니다. 가상환경, 캐시 폴더, 이미지 폴더, 기존 백업 폴더와 사용자 데이터는 백업 복사 범위에 넣지 않았습니다. 개인 데이터는 이동·초기화하지 않고 해시만 기록했습니다.

해당 백업에는 파일 이동 대응표 `migration-map.json`, 기존 데이터 해시 `user-data-hashes.json`, 이번에 사용한 이동·검증 보조 스크립트도 보관했습니다. 보조 스크립트를 다시 실행할 필요는 없습니다.

이전 버전을 복구하려면:

1. 실행 중인 앱을 종료합니다.
2. 별도의 복원 폴더를 새로 만듭니다. 현재 폴더 위에 덮어쓰면 새 패키지와 이전 파일이 섞일 수 있으므로 새 폴더에서 복원하세요.
3. 백업의 원래 `*.py`, `start.bat`, `requirements*.txt`, `README.md`, `.gitignore`, `ui_styles.css`, `advanced-verified-examples.json`, `translations/`, `.streamlit/`을 복원 폴더에 복사합니다. `migration-script.py`, `path-fix-script.py`, `verify-migration.py`, 해시·이동 대응표는 실행 소스가 아니므로 복사하지 않아도 됩니다.
4. 현재 프로젝트의 `data/`를 별도로 복사하거나 `MLB_ANALYTICS_DATA_DIR`로 기존 데이터 위치를 지정합니다. 기존 개인 데이터는 삭제하지 마세요.
5. 복원 폴더에서 Python 가상환경을 새로 만들고 의존성을 설치한 뒤 `start.bat`으로 실행합니다. 가상환경은 경로를 포함하므로 폴더 간 이동보다 재생성을 권장합니다.

이 프로젝트에서 Git 추적 파일은 확인할 수 없었습니다. 다른 Git 저장소로 옮길 때 이미 등록된 개인 파일이 있다면 `.gitignore`만으로 추적이 중단되지 않는다는 점에 주의하세요.
