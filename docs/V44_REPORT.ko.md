# MLB AI Analytics Pro 4.4 — Statcast 구현 보고서

## 추가한 기능

기존 4.3.1 폴더 구조, 기본·고급 통계, 다크 네이비 테마, 검색·즐겨찾기·수상·언어 기능을 유지했습니다. `start.bat`과 요구 패키지는 변경하지 않았고 새 의존성은 없습니다.

- **Statcast 분석 메뉴**: 선수와 시즌, 타격·투구 범주를 기존 선택기와 연결했습니다. 날짜를 선택하고 버튼을 누를 때만 새 Statcast 데이터를 조회합니다.
- **타격**: 평균/최대 타구 속도, 평균 발사각, Hard-Hit%, Barrel%, Sweet-Spot%, xBA·xSLG·xwOBA. 공식 전체 시즌 값과 선택 기간 직접 집계를 별도 표시합니다.
- **타격 차트**: 속도 히스토그램, 속도/발사각 산점도, 월별 속도·Hard-Hit%·Barrel%, 타구 유형별 분류, 결과 필터가 있는 타구 분포도입니다.
- **투구**: 평균/최대 구속, 평균 회전, 릴리스 익스텐션, 구종 사용률·Whiff%, pfx 무브먼트, 공식 xERA를 표시합니다. 실제 반환된 구종만 표에 포함하고 미분류 구종도 보존합니다.
- **투구 차트**: 구종 필터, 타자별 존 정규화 또는 ft 단위 위치, 표본 50개 이상에서 선택 가능한 2D 빈도 히트맵, 구종별 일관된 색상의 pfx 산점도입니다.
- **비교**: 이전 시즌을 별도 조회해 차이와 표본을 확인할 수 있습니다. 기존 선수 비교 화면에는 선택 조회 방식의 Statcast 비교를 추가했습니다. 투수는 구종 합집합에서 구종을 선택하며 던지지 않은 구종의 측정값을 만들지 않습니다.
- **AI**: 기존 AI 분석 화면의 Statcast 모드, Statcast 보고서·질문 기능과 비교 보고서를 추가했습니다. Python이 계산한 월별·구종별·위치 요약, 제공 상태, 분모, 출처만 전달합니다. 원시 투구 행은 전송하지 않습니다.
- 모든 새 화면 문구·설명·축·로딩·오류·AI 요청에 한국어/영어 번역을 추가했습니다. 공식 구종명과 원자료 이벤트 코드는 원문을 유지하며 구종 설명은 번역합니다.

## 데이터 출처와 실제 접근 확인

주 출처는 **Baseball Savant의 공개 CSV 다운로드**입니다. [공식 CSV 필드 문서](https://baseballsavant.mlb.com/csv-docs), [Statcast Search](https://baseballsavant.mlb.com/statcast_search), [공식 기대 지표 리더보드](https://baseballsavant.mlb.com/leaderboard/expected_statistics)를 확인했습니다.

- 투구/타구 원자료: `/statcast_search/csv`, 선수 MLBAM ID 필터, 날짜 경계, `hfGT=R|`, 상세 행 형식으로 조회합니다.
- 공식 타격 시즌 지표: `/leaderboard/statcast?type=batter&year=...&min=0&csv=true`.
- 공식 기대 지표: `/leaderboard/expected_statistics?type=batter|pitcher&year=...&min=0&csv=true`. 반환된 선수 ID와, 제공되는 경우 연도를 다시 검사합니다. 날짜 필터와 독립적인 **시즌 전체** 값임을 표시합니다.
- 리더보드는 모든 선수의 작은 시즌 요약 표를 한 번 받아 ID로 선택합니다. 전체 MLB 투구 이벤트를 다운로드하지 않습니다.
- [pybaseball의 선수별 조회 구현](https://github.com/jldbc/pybaseball/blob/master/pybaseball/statcast_batter.py)과 [투구 구현](https://github.com/jldbc/pybaseball/blob/master/pybaseball/statcast_pitcher.py)을 조사했습니다. 기존 `requests`와 표준 CSV 도구로 필요한 범위만 구현해 pybaseball 의존성을 추가하지 않았습니다.
- [MLB 이용조건](https://www.mlb.com/official-information/terms-of-use)과 Savant `robots.txt`를 확인했습니다. 조회 시 robots 응답은 전체 에이전트에 빈 Disallow였습니다. 이를 무제한 이용·재배포 허가로 간주하지 않으며, 제한 응답을 우회하지 않습니다. 403/429는 재시도하지 않고 중단합니다. 인증·유료 API는 사용하지 않았습니다.

2026-11-04 실제 조회에서 다음을 확인했고, 응답 주소·조회 시각·표본·요약을 `docs/statcast-live-evidence.json`에 저장했습니다.

| 선수/범주 | 조회 구간 | 확인한 결과 |
|---|---|---|
| 오타니, MLBAM 660271, 타격 | 2024-09-19 | 22개 투구 행, 타구 관측과 공식 2024년 시즌 타격·기대 지표 반환 |
| 폴 스킨스, MLBAM 694973, 투구 | 2024-05-11 | 84개 투구 행, 구종·속도·회전·위치·pfx와 공식 2024년 xERA 반환 |
| 오타니, 빈 비시즌 구간 | 2024-01-01 ~ 01-31 | 빈 관측값을 정상 처리 |

실제 전체 시즌 원자료 다운로드를 검증 목적으로 추가 수행하지는 않았습니다. 전체 기간 분할·실패·중복 처리 등은 자동 테스트로 검증했습니다. 시즌별 원자료 집계와 공식 시즌 리더보드는 데이터 처리·분모·제공 범위가 달라 수치가 반드시 같지는 않습니다.

## 계산식과 분모

| 지표 | 선택 기간의 직접 집계 |
|---|---|
| 평균/최대 EV | `type=X`인 인플레이 타구 중 유효 `launch_speed`의 평균/최대, mph |
| 평균 LA | 인플레이 타구 중 유효 `launch_angle`의 평균, 도 |
| Hard-Hit% | 95 mph 이상 타구 / 속도가 제공된 인플레이 타구 × 100 |
| Sweet-Spot% | 8~32도 타구 / 각도가 제공된 인플레이 타구 × 100 |
| Barrel% | 원자료 `launch_speed_angle=6` / 분류 1~6이 제공된 타구 × 100. 임의 속도·각도 문턱으로 배럴을 만들지 않음 |
| 구종 사용률 | 해당 구종 행 / 조회된 전체 투구 행 × 100. 미분류 구종도 분모에 포함 |
| 구속·회전·익스텐션 | 해당 측정값이 있는 투구만 평균/최대 계산. 단위는 mph·rpm·ft |
| Whiff% | 인식된 헛스윙 / 인식된 스윙 × 100. 투구 수나 타석 수를 분모로 사용하지 않음 |
| 수평·수직 pfx | 각각 `pfx_x`, `pfx_z`의 유효 관측 평균 × 12, in |

Whiff의 분자 분류는 `swinging_strike`, `swinging_strike_blocked`, `missed_bunt`, `swinging_pitchout`입니다. 분모에는 위 항목과 `foul`, `foul_tip`, `hit_into_play`, `foul_bunt`, `bunt_foul_tip`, `foul_pitchout`을 포함합니다. 실제 분류 목록과 분모를 요약에 보존하며 **직접 집계 Whiff%**로 표시합니다. 원출처의 공식 리더보드 처리 규칙과 동일하다고 단정하지 않습니다.

공식 시즌 카드는 위 계산값으로 대체하지 않고 발표 컬럼을 사용합니다. 표시 표본은 리더보드의 BBE 또는 PA이며, xERA의 PA 표본이 ERA 계산의 이닝 분모라는 뜻은 아닙니다. xBA·xSLG·xwOBA·xERA의 독자 모델을 만들거나 이벤트별 기대값을 단순 평균해 시즌 지표로 제시하지 않습니다.

## 좌표와 데이터 품질

- 투구 위치는 실제 `plate_x`, `plate_z`를 사용하며 ft, 포수 시점입니다. 오른쪽이 x 양수입니다.
- 기본 존 정규화는 각 투구의 `sz_bot`, `sz_top`으로 계산합니다. 존 정보가 없거나 상단이 하단 이하인 행은 정규화 차트에서 빠지지만 원자료나 다른 지표에서 삭제하지 않습니다. ft 모드는 측정된 타자별 존을 겹쳐 표시합니다.
- 공식 문서에 따라 2025년까지는 홈플레이트 앞면 위치이고 2026년부터는 중앙 위치 및 ABS 존 기준임을 화면에서 구분합니다. 서로 다른 시즌의 위치 정의가 완전히 같다고 가정하지 않습니다.
- AI의 존 내부 요약은 투구 중심이 17인치 폭과 해당 타자 존의 사각형 안에 있는 비율입니다. 공식 스트라이크 판정률이 아닙니다.
- 무브먼트는 일관되게 pfx 필드만 사용합니다. 중력 포함 총 낙차나 리그 평균 대비 차이, 별도 `api_break_*` 필드와 혼합하지 않습니다.
- 타구 분포도는 `hc_x−125`, `199−hc_y`로 홈을 원점에 놓은 원자료 좌표 도식입니다. 방향은 [pybaseball의 좌표 처리 구현](https://github.com/jldbc/pybaseball/blob/master/pybaseball/plotting.py)과 대조했습니다. 실제 구장 경계나 ft 단위 비거리, 정확한 착지점으로 표현하지 않습니다. 좌표가 없으면 위치를 추정하지 않고 안내합니다.
- 선수 ID·시즌·정규시즌 여부·날짜를 검증합니다. 중복은 `game_pk + at_bat_number + pitch_number`로만 판단합니다. 같은 식별자에 값이 충돌하면 조용히 선택하지 않고 오류로 중단합니다.
- 범위 밖 행의 수와 실제 중복 제거 수를 보존합니다. 원자료의 결측값을 0으로 대체하지 않습니다. 월별 누락 구간은 빈 값으로 남기고 선을 연결하지 않습니다.

## 제공 불가 항목과 한계

- Statcast 원자료는 2015년부터 현재 시즌까지 지원합니다. 추적 시스템과 제공 범위가 시대별로 다르며, 2015~2016년 구속은 출처 문서상 보정된 PITCHf/x 자료입니다. 2017년 이후 구속과의 단순 비교에도 이력을 고려해야 합니다.
- 원자료 EV/LA에는 출처에서 보정·추정한 값이 포함될 수 있습니다. 앱이 새로 추정하거나 결측값을 채우지는 않습니다.
- 검증된 동일 기준의 전체 MLB 평균을 확보하지 못해 **리그 평균은 N/A**입니다. 리더보드 선수별 비율을 단순 평균하지 않습니다.
- 공개 리더보드 또는 원자료가 없는 선수·시즌·항목은 N/A입니다. 기존 OPS+·wRC+·ERA+와 과거 시즌 wOBA/FIP의 제한도 그대로 유지합니다.
- 포스트시즌은 이번 UI에서 포함하지 않습니다. 원자료는 R 정규시즌만 요청하고 검증합니다.
- 작은 표본, 다른 조회 기간, 구종 구성 차이와 잠정 시즌 자료를 함께 고려해야 합니다. 한 지표로 전체 선수 우열이나 인과관계를 확정하지 않으며 성적 예측 모델은 추가하지 않았습니다.

## 성능과 장애 처리

- 원자료 캐시는 선수 ID·시즌·타격/투구·시작일·종료일별 **15분**, 최대 256개입니다. 작은 시즌 리더보드는 시즌·범주·표 종류별 **1시간**, 최대 32개입니다.
- 기간을 겹치지 않는 최대 31일 구간으로 나누고 순차 조회합니다. 요청 시작 사이에 최소 1초 간격을 둡니다. 연결/응답 제한 시간은 5/45초입니다.
- 일시적인 네트워크·서버 오류만 최대 3회 시도하며 지수 대기합니다. 403/429는 중단합니다. 응답은 최대 16 MB, 구간 행 수가 25,000개 이상이면 더 짧은 기간을 요청하도록 중단합니다. 초과 행을 잘라서 합계로 표시하지 않습니다.
- 전체 기간이 완료되기 전에는 완성 집계를 저장하지 않습니다. 성공한 구간 캐시는 재시도에 재사용합니다. 진행률을 표시하며 Streamlit 실행 중지 기능이나 더 짧은 날짜 범위로 조절할 수 있습니다.
- 새 메뉴를 열거나 위젯을 바꾸는 것만으로 다운로드하지 않습니다. 성공한 결과는 같은 선수·시즌·범위의 화면 재실행에서 재사용합니다. 기존 기록 새로고침은 Statcast 캐시와 불러온 상태도 비웁니다.
- 원자료 조회 실패 때도 확보된 공식 시즌 값과 기존 MLB 화면은 유지합니다. AI는 compact 요약만 받으며 버튼/질문 전송 시에만 생성합니다.

## 추가·수정한 파일

- 신규 서비스: `services/statcast_service.py`
- 신규 분석: `analytics/statcast_hitting.py`, `analytics/statcast_pitching.py`, `analytics/statcast_context.py`
- 신규 화면: `components/statcast_ui.py`, `components/statcast_charts.py`
- 통합 수정: `components/dashboard.py`, `components/ui_components.py`
- 번역: `translations/ko.json`, `translations/en.json` (기존 항목은 유지하고 새 키 추가)
- 검증: `tests/test_statcast.py`, `tests/test_statcast_ui.py`, `scripts/check_statcast_live.py`
- 문서·근거: `README.md`, 이 보고서, `docs/statcast-live-evidence.json`, `v44-test-results.log`

## 검증과 실행

최종 자동 테스트는 **165개 통과, 실패 0개**입니다. 기존 회귀 테스트 144개와 Statcast 테스트 21개를 실행했습니다. 선수 ID, 날짜/정규시즌 필터, 캐시, 결측값, 공식 분류, 분모, 중복·충돌, 좌표, 요청 제한·재시도·크기 제한, 언어 전환, 로딩·재시도·비교, compact AI 문맥과 명시적 생성 동작을 포함합니다.

- `scripts.check_statcast_live`: 실제 타격·투구 및 빈 구간 확인 통과.
- `scripts.check_startup`: Streamlit 서버 시작·health 응답 확인 통과.
- `scripts.check_launcher`: 실제 `start.bat`의 서버 시작 및 생성한 프로세스 정리 확인 통과.
- 기존 계산·출처 모듈, 수상·즐겨찾기 로직, 테마 파일은 백업과 바이트 단위로 동일합니다. 기존 번역 항목의 값도 유지됐습니다.
- 기존 `favorites.json`, `settings.json`의 작업 전후 SHA-256 해시가 동일합니다.
- 이번에 실제 Ollama 문장 생성과 Playwright 전체 브라우저 시각 검증은 추가 실행하지 않았습니다. AI 문맥·버튼·언어·생성 호출은 mock으로, 로딩된 타격·투구·비교 화면은 Streamlit AppTest로 검증했습니다.

실행은 기존처럼 **`start.bat` 더블클릭**입니다. 현재 컴퓨터에서 검증한 수동 명령:

```powershell
.\.venv-test\Scripts\python.exe -m streamlit run app.py
.\.venv-test\Scripts\python.exe -m unittest discover -v
.\.venv-test\Scripts\python.exe -m scripts.check_statcast_live
```

Git을 사용할 수 없어 작업 전 소스·테스트·설정·번역·문서를 `.backups/pre-v44-20261104-163643/`에 백업했습니다. 가상환경·캐시·사용자 데이터를 복제하거나 초기화하지 않았습니다. 이전 버전은 앱을 종료한 뒤 백업 소스를 새 폴더에 복사하고, 개인 `data/`는 보존해 연결하는 방식으로 복원할 수 있습니다.
