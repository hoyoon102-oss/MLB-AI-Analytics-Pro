# Version 4.9 출시 준비도

**최종화 결과:** 254개 pytest 통과(57.99s), 커버리지 87%, Ruff/import/의존성 검사 통과. 실제 MLB 타격·투구/이름 검색/하루 Statcast/로컬 Ollama 모델 목록, Windows start.bat, 현재 UI 1440/390px 고정 자료 검증을 완료했습니다. 세부 근거와 최종 판정은 [FINAL_HANDOVER.ko.md](FINAL_HANDOVER.ko.md)를 기준으로 확인하세요. 아래 표는 최종화 이전의 4.9 초기 QA 기록으로 보존합니다. 태그/공개 배포는 하지 않았습니다.

검증 환경: Windows, Python 3.10.4. 사용자 기준일 2026-11-08. 공개 배포/원격 저장소 생성/push/원격 릴리스는 수행하지 않았습니다.

| 영역 | 결과 | 증거 및 범위 |
|---|---|---|
| 자동 테스트 | PASS | 새 .venv-qa에서 251 passed in 41.71s, v49-final-tests.log |
| 코드 품질 | WARNING | 측정 대상 4434 statements, 572 missed, 총 87% coverage (.backups/v49-coverage.json). 전수 정적 분석/린트 미실시 |
| 통계 회귀 | PASS | 기존+추가 기본 비율/이닝/FIP/wOBA/백분위/유사도/커리어/이적·겸업·결측 고정 예제. 공급원 전체 역사 정확성 보장은 아님 |
| 데이터 최신 정확성 | NOT TESTED | 이번 작업은 실제 MLB/Savant 전체 API 재조회 안 함. DATA_QUALITY.md 참고 |
| DB 무결성 | PASS | 기존 LOCAL DB를 mode=ro로 검사: integrity_check=ok, FK 위반 0, schema=1 |
| DB 복구/동시성 | PASS | 임시 DB 초기화/미래 버전 거부/중복/rollback/캐시 만료/손상 복구/18개 병렬 작업/백업·복원/재시작 테스트 |
| 사용자 데이터 보호 | PASS | pytest 임시 경로, CLOUD 두 사용자 세션의 즐겨찾기/프리셋/언어 격리. 기존 사용자 파일 삭제 없음 |
| 보안 | WARNING | SQL 바인딩/HTML escape/CSV 수식 방어 확인, CLOUD Ollama/DB 차단. CVE 스캔/ACL/침투시험은 미실시 |
| 의존성 | PASS | 새 venv requirements+dev 설치 성공(v49-clean-install.log), pip check: No broken requirements found |
| LOCAL 기동 | PASS | scripts.check_startup 건강 응답 ok, app import 성공, 기존 start.bat 변경 없음 |
| LOCAL 실모델 AI | NOT TESTED | Ollama 모킹 회귀 통과. 실제 설치 모델 추론은 미실시 |
| CLOUD 코드 경계 | PASS | CLOUD 무네트워크 서비스 검사, 두 세션 격리, API Timeout 상태 AppTest 통과 |
| Linux/Community Cloud | NOT TESTED | Python 3.11 Ubuntu workflow 작성, 실제 실행/호스팅 안 함 |
| GitHub 준비 | WARNING | workflow/ignore/문서 준비. Git 실행 파일을 못 찾아 status/추적 비밀/원격 설정 검증 불가 |
| 데이터 사용 조건 | BLOCKED | 공개 재배포 허가 확정 안 됨. 배포 승인도 없음 |
| 성능 | WARNING | 고정 자료 측정만 완료. 실제 트래픽/메모리/동시 사용자 한도 미측정 |
| UI/UX | WARNING | 기존 페이지 AppTest 회귀 및 한영/오류 대응 통과. 실제 브라우저 폭별/모바일 육안 검사는 미실시 |
| 문서 | PASS | README, CHANGELOG, TESTING, SECURITY, ARCHITECTURE, DEPLOYMENT, DATA_QUALITY, V49_REPORT 작성 |

의존성 검증 버전: Streamlit 1.65.0, pandas 2.3.3, numpy 2.2.6, pytest 8.4.2. 최신/보안 무결점을 의미하지 않습니다. Python 3.11/Linux는 아직 실행 증거가 없습니다.

## 실제 성능 측정

v49-benchmark.json: 3개 독립 프로세스 고정 자료 중앙값. 최초 조회는 검색 5.921 ms, 선수 통계 3.671 ms, 리더보드 4.018 ms, Statcast 요약 3.171 ms, 커리어 3.255 ms. 네트워크 지연은 모사하지 않았습니다. 재시작 캐시 단계는 모든 fixture에서 외부 source 호출 0회였습니다. 파일의 v48 키는 기존 도구의 단계 이름입니다.

v49-analytics-benchmark.json: 각 100회, 5개 묶음 중앙값. 백분위 0.091 ms, 유사도 0.076 ms, 20시즌 커리어 합계 0.370 ms, 100행 리더보드 필터 0.911 ms. 실제 서비스 지연/향상률/공개 서버 용량을 뜻하지 않습니다.

## 남은 일 (우선순위)

1. 공개 전 데이터·이미지·CSV 재배포 조건 검토와 소유자 배포 승인. 현재 공개 배포 BLOCKED.
2. Git 설치 후 추적 파일/비밀 정보 점검, 코드 라이선스 선택. 자동 history rewrite 없음.
3. 실제 GitHub Ubuntu CI와 Python 3.11 검증, Linux 비공개 staging 설치.
4. 서버 자원 측정 및 요청량/동시성 제한 설계. 공용 캐시 새로고침 영향 검토.
5. 실제 API·Ollama·브라우저 화면 크기별 수동 회귀. durable multi-user 저장이 필요하면 인증/격리 설계를 먼저 승인.

소스 체크포인트는 .backups/v49-before-*.zip입니다. 개인 데이터 백업과는 별개입니다. 세부 변경 및 실행법은 V49_REPORT.ko.md를 보세요.
