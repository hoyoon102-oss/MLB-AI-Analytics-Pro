# GitHub 업로드 사전 검토 — 4.9

점검 기준일: 2026-11-08. **업로드 후보 목록 준비 완료, 업로드 승인 전입니다.** commit/stage/tag/push/원격 저장소 생성/공개/삭제는 하지 않았습니다.

## 범위와 결과

초기 후보 147개를 점검하고 이 보고서와 후보 목록 2개를 추가했습니다. 최종 후보 수는 GITHUB_UPLOAD_FILES.txt의 행 수와 같습니다. `.gitignore` 외 기존 앱·테스트·런처·의존성·개인 파일은 수정하지 않았습니다. 업로드 준비 변경은 `.gitignore` 및 `docs/GITHUB_UPLOAD_REVIEW.ko.md`, `docs/GITHUB_UPLOAD_FILES.txt`, `docs/GITHUB_RIGHTS_REVIEW_FILES.txt`뿐입니다. 이전 ZIP/릴리스 체크포인트와 그 해시는 수정하지 않았습니다.

후보 추출에는 `rg --files --hidden --no-require-git --no-ignore-global --no-ignore-parent -g '!.git/**'`를 사용했습니다. 현재 Git 실행 파일 및 이 경로의 Git 메타데이터를 확인할 수 없어 **실제 git status/git ls-files/원격 추적·이력 검사는 하지 못했습니다.** 이 목록은 현재 .gitignore를 적용한 신규 저장소의 미추적 파일 후보이며 실제 Git staging 결과가 아닙니다. 추후 Git의 전역 ignore/attributes/이미 추적된 파일에 따라 결과가 달라질 수 있습니다.

## 개인 데이터와 비밀 정보

| 항목 | 결과 |
|---|---|
| 후보 텍스트 | 일반적인 AWS/GitHub/OpenAI 키, 비밀 키 PEM 헤더, 인증정보 포함 URL, 비밀번호/토큰 할당, 이메일, 사용자 절대 경로 패턴 발견 0 |
| .env / secrets.toml | 실제 파일은 현재 프로젝트에서 확인되지 않음. .env.example은 비밀 값 없는 설정 예시 |
| SQLite | 실제 LOCAL DB는 프로젝트 밖 기본 저장소에 있음. 후보에 DB/WAL/SHM/journal 없음. DB/보조파일 제외 규칙 유지·보강 |
| 즐겨찾기/언어 | data/favorites.json, data/settings.json 존재. data/ 전체 제외. 값/선수 목록은 보고서에 복사하지 않음 |
| 프리셋 | data/leaderboard_presets.json은 현재 없지만 경로와 파일명 제외 규칙 적용 |
| 로그 | 과거 로그 5개에서 사용자 로컬 경로 발견. 모두 *.log로 제외. 원문/개인 경로는 표시하지 않음 |
| 백업 | .backups/ 전체 제외. 이전 소스·해시·ZIP은 로컬에 유지. 백업 아카이브는 풀어서 비밀 검사하지 않음 |
| 가상환경/캐시 | .venv*/, __pycache__/, .pytest_cache/, .ruff_cache/, .coverage 등 제외 |
| 스크린샷 | 후보 PNG 2개 육안 확인. 앱 UI/공개 선수명만 보이고 사용자 계정·로컬 경로 없음. PNG 텍스트/EXIF 메타데이터 키 없음 |
| 보존 검증 | 앱/테스트/번역/수동 검사/개인 JSON/실제 DB/런처/테마 등 111개 보호 파일의 전후 해시 비교 |

이 검사는 패턴 기반 점검이며 모든 형태의 비밀 정보가 없다는 보증은 아닙니다. 제외한 가상환경/백업 전체 내용이나 운영체제 전체, 외부 저장소는 검사 범위가 아닙니다. 로컬 DB는 업로드 검사 때문에 연결하거나 변경하지 않았습니다.

`.gitignore`에 추가한 보호: 파일명 기반 favorites/settings/leaderboard_presets JSON, 추가 secrets.toml, PEM/KEY/P12/PFX, .aws/.ssh, 루트 IDE 설정, DB3와 보조파일, 추가 backup/bak 변형 및 backup/backups 폴더. 필요한 소스·번역·테마·.env.example은 제외하지 않았습니다. `.gitignore`는 ZIP 전체나 GitHub 웹 업로드의 내용 필터가 아니므로, 폴더 전체를 압축해 올리지 마세요. 이미 추적한 파일에는 ignore만으로 보호되지 않습니다.

## 업로드 후보

전체 상대 경로는 [GITHUB_UPLOAD_FILES.txt](GITHUB_UPLOAD_FILES.txt)에서 확인하세요.

- 앱: app.py, analytics/, components/, services/, utils/, translations/
- 실행/설정: start.bat, requirements*.txt, pytest.ini, .env.example, .streamlit/config.toml, .gitignore
- 검증: tests/, scripts/, .github/workflows/tests.yml
- 문서/예제: README.md, PROJECT_SUMMARY.md, CHANGELOG.md, docs/

**후보라는 이유만으로 공개 권한이 확인된 것은 아닙니다.** 권리 검토 목록은 [GITHUB_RIGHTS_REVIEW_FILES.txt](GITHUB_RIGHTS_REVIEW_FILES.txt)입니다. 해당 파일을 자동 삭제·이동·Git 제외하지 않았습니다. 테스트 예제와 상수를 제거하면 검증/계산이 달라질 수 있어 임의로 바꾸지 않았습니다.

## 개인정보와 별개인 권리 검토

1. `tests/advanced-verified-examples.json`은 MLB 응답의 저장 예제입니다. 테스트 및 브라우저 검증 도구가 사용하므로 유지했지만 공개 재배포 조건을 별도로 확인해야 합니다.
2. `docs/*-live-evidence.json` 4개는 Statcast/랭킹/커리어/리더보드 수집 결과입니다. 사용자 비밀 정보는 아니지만 외부 자료의 공개 재배포 여부를 검토해야 합니다.
3. `analytics/advanced_stats_sources.py`의 FanGraphs 시즌 상수와 해당 값을 설명하는 테스트/문서가 있습니다. 소스 공개 라이선스와 데이터 권리를 동일하게 취급하지 마세요.
4. `docs/images/v49-player-*.png` 2개는 앱의 QA 스크린샷입니다. 선수 사진은 포함하지 않으며 저장된 통계/공개 선수명과 앱 UI가 포함됩니다. 이미지 전체가 데이터 권리 검토에서 면제되는 것은 아닙니다. 이전 선수 사진 포함 ui-preview/는 제외했습니다.
5. LICENSE/NOTICE 파일은 현재 없습니다. 코드 라이선스는 소유자가 선택해야 하며 자동으로 MIT 등으로 지정하지 않았습니다. 의존성 라이선스와 코드 저작권/외부 데이터 권리는 각각 별개입니다. 가상환경을 업로드하지 않으며 설치 의존성은 requirements로 제공합니다.

확인한 공식 안내:

- [MLB 이용약관](https://www.mlb.com/official-information/terms-of-use): 공개 재배포 허가는 확정하지 않았습니다.
- [FanGraphs 이용약관](https://www.fangraphs.com/about/terms-of-service): 저작권·이용 조건 확인이 필요합니다.
- [GitHub 저장소 라이선스 안내](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository): 코드 재사용 조건은 소유자의 라이선스 선택과 구분해야 합니다.

공개 허가/불법 여부에 대한 포괄적 법률 판정을 내리지 않았습니다. 권한이 불명확한 자료를 공개 승인된 것으로 표시하지 않았습니다.

## 승인 전 남은 확인

- Git 설치 후 먼저 읽기 전용 `git status --short --untracked-files=all`, `git ls-files`, `git status --short --ignored`, `git remote -v`로 실제 상태를 확인합니다. 원격 URL에 토큰이 있으면 그대로 공유하지 마세요.
- 이 폴더는 현재 저장소가 아니므로 위 명령은 Git 저장소가 준비된 뒤에만 동작합니다. 이번 작업에서 git init/add/commit도 수행하지 않았습니다.
- 이후 추가한 파일/변경사항은 다시 검사해야 합니다. 업로드 목록은 현재 시점의 스냅샷입니다.
- 공개 범위, 외부 통계/상수/스크린샷 재배포, 코드 라이선스와 최종 파일 목록을 확인하고 명시적으로 승인하기 전에는 업로드하지 않습니다.

**판정: 개인정보 제외 규칙과 검토 자료 준비 완료. 실제 업로드/공개는 승인 및 권리 검토 대기.**
