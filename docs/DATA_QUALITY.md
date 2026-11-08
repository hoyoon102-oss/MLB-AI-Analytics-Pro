# 데이터 품질 및 출처

MLB ID/시즌/범주/정규시즌을 검증하는 기존 파이프라인과 이적 선수 합계 우선 처리, 중복/불완전 집합 거부를 유지했습니다. 출처/조회 시각/캐시 시각을 유지하며 만료 DB 값을 최신 자료로 대신 제공하지 않습니다. 손상 캐시 태그 검사와 잘못된 TTL 설정의 기본값 처리를 보강했습니다.

| 출처 | 자료 / 방식 | 제한 |
|---|---|---|
| https://statsapi.mlb.com/api/v1/ | 선수/팀/시즌/수상 JSON HTTPS | 가용성·과거 기록 완전성 보장 없음. 공개 API가 재배포 허가를 의미하지 않음 |
| https://baseballsavant.mlb.com/csv-docs | 투구 CSV, 시즌 리더보드, 출처 발표 백분위 | 2015년 이후, 추적 누락·필드/장비 변경, 예상 지표와 관측값 구분 |
| https://www.fangraphs.com/tools/guts?type=cn | 코드에 기록한 시즌별 wOBA/FIP 상수 | 2020~2025 snapshot. 없는 연도는 N/A |
| img.mlbstatic.com | 선수 사진 HTTPS | 이미지 권리 별도 확인 필요 |

[CSV 문서](https://baseballsavant.mlb.com/csv-docs)와 [FanGraphs 상수 표](https://www.fangraphs.com/tools/guts?type=cn)를 확인했으며 2024 예제에 사용한 상수와 일치합니다. 모든 연도의 원자료를 다시 내려받아 검증한 것은 아닙니다. [MLB 이용약관](https://www.mlb.com/official-information/terms-of-use)을 공개 이용 전 검토해야 합니다. 서비스별 자동 수집·캐시·상업 이용·CSV 재배포 조건의 포괄적 허가는 확인되지 않아 공개 배포는 보류합니다.

OPS+/ERA+/wRC+는 필요한 검증된 보정 자료가 없어 N/A입니다. 단순 리그 비율을 해당 지표로 표시하지 않습니다. wOBA/FIP와 로컬 백분위/유사도는 로컬 계산이며 출처 발표 백분위와 구분합니다. 기간 Statcast 집계와 전체 시즌 발표 지표는 범위가 다릅니다.

발견된 한계: 현재 연도는 시즌 종료 후에도 보수적으로 짧은 TTL, 역사적 팀/리그 누락 시 필터 제한, 작은 표본의 순위 불안정, 겸업 범주별 모집단 차이, 상수 snapshot 갱신 필요. 검증되지 않은 값은 0이나 추정값으로 보충하지 않습니다. 실서비스 API의 최신 응답 전수 검증은 미실시입니다.

최종화 추가 확인: 부분 실패 이력/커리어의 영구 캐시 저장·재사용을 막고 재조회하도록 수정했습니다. 선수 검색과 2024-09-19 Ohtani 하루 Statcast 실제 조회는 final-live-checks.json에 별도 기록했습니다. 전 시즌 전수검증을 의미하지 않습니다.
