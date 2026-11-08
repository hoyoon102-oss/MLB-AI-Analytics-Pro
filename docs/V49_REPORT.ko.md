# Version 4.9 작업 보고서

4.9는 기존 앱을 유지하면서 pytest·CI·보안 경계·배포 문서를 추가한 버전입니다. 실제 공개 배포 준비 완료를 선언하지 않습니다.

## 주요 변경

- pytest로 기존 테스트 재사용, 임시 DB/설정 경로와 외부 HTTP 차단.
- 통계 수동 예제 검증, 손상 캐시 복구, CLOUD 사용자 격리 및 UI 오류 대응 검사.
- LOCAL은 기존 즐겨찾기/프리셋/언어/SQLite/Ollama 유지. CLOUD는 개인 설정을 세션에만 저장하고 SQLite/Ollama/관리자 화면 차단.
- 잘못된 캐시 태그와 TTL 환경변수에 대한 복구 강화.
- GitHub Actions는 테스트/의존성 검사/import만 수행. 배포·push는 하지 않음.

수정 파일: .gitignore, README.md, requirements-dev.txt, components/{dashboard,ai_ui,system_performance_ui,ui_components}.py, services/{ai_analyst,cache_manager,cache_policy,database}.py, utils/{favorites,i18n,leaderboard_presets}.py. 새 파일은 utils/config.py, pytest.ini, tests/conftest.py, tests/test_deployment_security.py, tests/test_statistics_validation.py, scripts/benchmark_analytics.py, .env.example, .github/workflows/tests.yml, CHANGELOG.md와 문서/측정 JSON입니다. 기계 판독 목록은 v49-file-changes.json에 있습니다.

## 보호 및 점검

수정 전 117개 소스/설정/문서를 .backups/v49-before-*.zip에 보관했습니다. 개인 데이터는 이 소스 ZIP에 포함하지 않았고 원래 위치에 유지합니다. 실제 DB는 읽기 전용으로 integrity_check=ok, foreign_key_check 빈 결과, user_version=1을 확인했습니다. 실제 DB에서 삭제/복원/손상 테스트는 하지 않았습니다.

보안 점검에서 SQL 값 바인딩, HTML 이름 escape, AI 컨텍스트 허용 필드, 고정 로컬 Ollama 주소, CSV 수식 이스케이프가 이미 적용되어 있음을 확인했습니다. DB/보조 파일 ignore와 CLOUD 경계를 보강했습니다. Git이 없어 추적 파일과 과거 비밀 유출 여부는 확인하지 못했습니다. 라이선스는 상의 없이 추가하지 않았습니다.

## 제한 및 다음 단계

OPS+/ERA+/wRC+ 및 없는 시즌 상수는 N/A입니다. 통계 공급원의 최신 원자료 전수 검증과 이용 허가는 별도 확인해야 합니다. CLOUD의 세션 설정은 재연결/재시작 시 사라질 수 있으며 인증 기반 계정 저장소가 아닙니다. 메모리 캐시 새로고침은 다른 세션의 공개 통계 캐시에도 영향을 줄 수 있습니다. SQLite는 LOCAL 단일 사용자 용도이며 공용 계정 데이터 저장소로 사용하지 않습니다.

Ollama 실모델 추론, Linux 실행, 실제 GitHub CI, 실제 API 최신 응답, 모바일/화면 폭별 실제 브라우저 검사는 이번 작업에서 실행하지 않았습니다. 공개 전 출처 권한 확인 → Git 추적 목록 검토 → Linux CI → 소규모 비공개 staging의 메모리/동시 접속 검증 순서로 진행하세요. 유료 서비스나 외부 DB는 연결하지 않았습니다.

## 실행 방법

기존처럼 start.bat을 더블클릭하세요. 기본 모드는 LOCAL입니다. 수동 실행은 `python -m streamlit run app.py`입니다. `.venv-qa`는 이번에 만든 설치 검증용 환경이며 기존 launcher는 변경하지 않았습니다.

테스트는 `.\.venv-qa\Scripts\python.exe -m pytest -q` 또는 개발 의존성을 설치한 환경의 `python -m pytest -q`로 실행합니다. 최종 결과/커버리지와 미검증 항목은 RELEASE_READINESS.md를 확인하세요.
