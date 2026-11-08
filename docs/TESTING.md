# 테스트 실행

```powershell
.\.venv-test\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt
.\.venv-test\Scripts\python.exe -m pytest -q
.\.venv-test\Scripts\python.exe -m pytest --cov=analytics --cov=services --cov=components --cov=utils
```

기존 unittest를 pytest에서 그대로 수집합니다. `tests/conftest.py`는 테스트마다 임시 DB/개인 폴더를 지정하고 메모리 캐시를 초기화합니다. HTTP는 모킹하지 않으면 실패합니다. Windows asyncio용 내부 루프백 소켓만 허용합니다. 기존 scripts/check_*_live.py는 실제 서비스가 필요한 별도 수동 검사이며 표준 CI에서 실행하지 않습니다. 보호 장치가 적용되는 pytest 명령을 사용하세요.

분류: `-m unit`, `integration`, `api`, `database`, `ui`, `regression`, `security`. 기존 파일의 역할을 기반으로 분류하며 일부 범주는 겹칩니다. PASS는 해당 고정 자료 조건의 성공입니다. 실제 모든 MLB 시즌의 정확성이나 브라우저 반응형 화면 전체를 보증하지 않습니다.

DB 테스트: 초기화/버전/인덱스/PK/중복/rollback/만료/손상 캐시/동시 연결/백업/복원/재시작을 임시 파일로 검사합니다. 통계 테스트: 검증 예제 JSON 및 수동 계산 예제로 기본 비율, 고급 지표, 이닝, 결측, 이적 합계, 겸업, 단축 시즌, 백분위/유사도/커리어를 확인합니다.

성능: `python -m scripts.benchmark_cache --runs 3 --output docs/v49-benchmark.json`, `python -m scripts.benchmark_analytics`. 결과 JSON은 고정 자료만 사용한 시간이며 네트워크·UI 시간과 다릅니다. 이전 benchmark 도구의 v48_cold/v48_restart 키는 측정 단계 이름이며 4.9 소스를 측정했습니다.

## 4.9 Final 검증 도구

- `python -m scripts.check_connections`: 실제 MLB 타격·투구 및 Ollama 모델 목록. 실행 전 `$env:MLB_CACHE_DISABLED="1"`로 개인 DB 쓰기를 피하세요. AI 생성은 하지 않습니다.
- `python -m scripts.check_final_live`: 선수 이름 1회·선수 하루치 Statcast, DB 캐시 비활성화. 결과는 docs/final-live-checks.json.
- `python -m scripts.check_final_browser`: Edge가 설치된 Windows에서 현재 UI를 고정 자료로 검증하고 1440/390px 스크린샷 저장. 개인 저장소는 임시 폴더, 실제 API/AI 생성은 사용하지 않습니다. 이미지 통계는 tests/advanced-verified-examples.json의 저장 예제이며 최신 조회가 아닙니다.
- `python -m scripts.check_launcher`: Windows start.bat과 실제 서버 기동/종료.
- `python -m ruff check app.py analytics components services utils scripts tests --select F401,F811,F821,F822,F823`: 미사용 import·재정의·정의되지 않은 이름 검사.

일반 테스트는 pytest로 실행하세요. unittest를 직접 실행하면 자동 임시 경로/HTTP 차단 fixture가 적용되지 않습니다. 최종 결과는 FINAL_HANDOVER.ko.md를 기준으로 읽으세요.
