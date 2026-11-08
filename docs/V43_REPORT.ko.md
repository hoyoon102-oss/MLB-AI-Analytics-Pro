# MLB AI Analytics Pro 4.3 구현 보고서

기존 4.2 구조에 고급 통계를 추가했습니다. 기본 기록, 검색, 즐겨찾기, 수상, 리그 비교, Ollama 분석, 한국어·영어 및 다크 네이비 테마를 유지합니다.

## 추가 기능

- 선수 기록 화면을 기본 기록 / 고급 기록 / 시즌별 추세 / 수상 경력 탭으로 구성했습니다.
- 고급 카드에 값, 리그 평균 또는 보정 지표 기준값, 차이, 설명 툴팁, 계산식과 출처를 표시합니다.
- 선수와 리그 비교, 두 선수의 고급 지표 비교, 지표 선택형 시즌 추세를 제공합니다. FIP/ERA, K%/BB%, ISO/BABIP를 함께 표시할 수 있습니다.
- 누락된 시즌은 0으로 채우거나 선으로 연결하지 않습니다.
- AI에 고급 지표, 출처, 시즌, 리그 평균, 차이와 시즌 변화량을 전달합니다. 기존 언어별 응답 및 근거·해석 구분 규칙을 유지합니다.

## 사용 가능한 지표

| 범주 | 지표 | 조건 |
|---|---|---|
| 타격 | ISO, BABIP, BB%, K%, BB/K | 필요한 MLB 원자료와 유효한 분모 |
| 타격 | wOBA | 필요한 원자료 및 2020–2025 시즌 상수 |
| 투구 | K/9, BB/9, HR/9, K/BB, K%, BB%, K-BB%, 피BABIP | 필요한 MLB 원자료와 유효한 분모 |
| 투구 | FIP | HR, BB, 사구, SO, 아웃 수 및 2020–2025 시즌 상수 |

투구 이닝은 먼저 아웃으로 변환합니다. 6.1이닝은 19아웃입니다. BB/K와 K/BB의 분모가 0이면 N/A입니다. FIP의 음수는 허용합니다. ISO는 가능하면 반올림된 AVG/SLG 대신 안타·총루타·타수로 계산합니다.

모든 제공 수치는 직접 계산한 값입니다. wOBA와 FIP도 공식 발표 선수값으로 표시하지 않습니다. 상수는 출처에 공개된 정밀도를 사용하므로 다른 제공자의 결과와 소수점 차이가 있을 수 있습니다.

## 제공하지 않는 지표와 제한

- OPS+, wRC+, ERA+: 검증된 선수별 공식 발표값과 구장·리그 보정 자료를 확보하지 못해 N/A입니다. 원시 리그 ERA나 OPS로 대체하지 않습니다.
- 위 세 지표의 100은 정의상 비교 기준입니다. 선택한 AL/NL의 실제 평균이나 선수 성적이 아닙니다.
- 2026년과 2020년 이전의 wOBA·FIP: 이 구현에 검토된 상수가 없어 N/A입니다. 인접 시즌 상수를 재사용하지 않습니다.
- 표본이 작거나 진행 중인 시즌의 수치는 해석에 주의가 필요합니다. 단일 지표로 우열이나 인과관계를 확정하지 않으며 예측 기능은 추가하지 않았습니다.
- MLB/AL/NL 평균은 기존 시즌별 팀 모집단 검증을 거쳐 원자료 합계의 비율로 계산합니다. 모든 팀에서 해당 항목이 확인되지 않으면 그 평균은 N/A입니다. 리그 평균 비교를 켜야 실측 리그 평균이 표시됩니다.
- 이적 선수는 기존 합산 시즌 기록 선택을 유지합니다. 여러 팀 기록만 있고 합산 기록을 구분할 수 없으면 임의 합산하지 않습니다. API가 선수 ID를 명시하면 요청한 ID와의 일치를 검사합니다.
- 외부 출처 장애가 다른 화면을 중단하지 않도록 새 고급 계산에는 외부 조회를 추가하지 않았습니다. 기본 MLB 조회 실패는 기존 처리 방식을 따릅니다.

## 데이터 출처와 조사

- 기본 원자료: MLB Stats API. `season`, `group`, `gameType=R`을 구분합니다. 실제 2024년 MLB ID 660271과 543037의 응답을 확인했고 `advanced-verified-examples.json`에 조회 시각·원자료·계산 결과를 저장했습니다.
- 상수: [FanGraphs Guts](https://www.fangraphs.com/tools/guts?type=cn), 검토일 2026-11-04. 2020–2025년 공개 시즌 상수만 작은 고정 자료로 수록했습니다. 실행 중 스크래핑이나 회원 전용 내보내기는 사용하지 않습니다.
- 계산 정의: [FanGraphs wOBA](https://library.fangraphs.com/offense/woba/), [FIP](https://library.fangraphs.com/pitching/fip/).
- [FanGraphs 이용조건](https://www.fangraphs.com/about/terms-of-service), [MLB 이용조건](https://www.mlb.com/official-information/terms-of-use), [pybaseball 문서](https://github.com/jldbc/pybaseball/blob/master/docs/fangraphs.md), [MLB Statcast 설명](https://www.mlb.com/glossary/statcast)을 검토했습니다. 공개 접근 가능성과 자동 수집·재배포 허가는 별개이므로 새 FanGraphs/Statcast 수집기는 연결하지 않았습니다. pybaseball 설치만으로 원출처 이용 허가나 선수 ID 일치가 보장된다고 가정하지 않았습니다. 유료 API는 사용하지 않습니다.
- Statcast의 이벤트 기반 wOBA나 xwOBA를 FanGraphs 시즌 가중치 wOBA와 섞지 않습니다. WAR 정의도 추가하지 않았습니다.

각 지표의 내부 메타데이터에 이름, 값, 시즌, 범주, 선수 ID, 정규시즌 여부, 출처, 계산식, 직접 계산/제공 불가 분류, 조회 시각, 제공 상태와 상수 근거를 저장합니다. 화면의 출처 펼치기에서 확인할 수 있습니다.

## 변경 파일

- 신규 계산·출처 모듈: `advanced_hitting.py`, `advanced_pitching.py`, `advanced_stats_sources.py`, `advanced_stats.py`
- 신규 화면 모듈: `advanced_stats_ui.py`
- 통합: `app.py`, `league_stats.py`, `league_ui.py`, `ai_analyst.py`, `ui_components.py`
- 번역: `translations/ko.json`, `translations/en.json`
- 실행: `requirements.txt`, `start.bat`
- 검증: `test_advanced_stats.py`, `check_advanced_live.py`, `advanced-verified-examples.json`, 기존 화면 테스트 4개 파일의 차트 개수 기대값
- 기록: `v43-source-inventory.json`, `v43-test-results.log`, 이 보고서

Git 실행 파일을 찾을 수 없어 Git 체크포인트 대신 `.backups/pre-v43-*`에 수정 전 최상위 파일과 번역 파일을 복사했습니다.

## 실행 방법

`start.bat`을 더블클릭합니다. 기본 `.venv`가 실행되지 않으면 이번에 설치·검증한 `.venv-test`를 사용합니다. 브라우저에서 안내되는 로컬 주소를 여세요.

직접 실행:

```powershell
.\.venv-test\Scripts\python.exe -m streamlit run app.py
```

기존 `.venv`는 제거된 Python 3.15 경로를 참조하고 있었습니다. 테스트 환경의 기존 Python 3.10과 Streamlit 1.65에서 검증했습니다. 패키지 저장소에 없는 기존 `streamlit>=1.66` 요구사항을 `>=1.65`로 수정하고 Windows 시간대 자료 `tzdata`를 추가했습니다.

자동 테스트:

```powershell
.\.venv-test\Scripts\python.exe -m unittest discover -v
.\.venv-test\Scripts\python.exe check_startup.py
```

검증 결과: 전체 자동 테스트 **142개 통과, 실패 0개**. ISO·BABIP·비율·FIP·이닝·결측값·0 분모·리그 기준·이적 시즌·선수 ID·언어 전환·기존 기능 회귀를 포함합니다. 전체 결과는 `v43-test-results.log`에 기록했습니다. MLB 실제 응답 확인도 통과했습니다. Streamlit 서버 시작 검증은 격리된 포트에서 health 응답을 확인했고 통과 후 해당 프로세스를 종료했습니다. AI의 실제 문장 생성 품질은 로컬 Ollama 모델에 따라 달라지며, 이번 검증에서 실제 모델 생성 테스트를 추가 실행하지 않았습니다.
