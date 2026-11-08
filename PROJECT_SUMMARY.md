# MLB AI Analytics Pro — 4.9 Final

## 프로젝트 소개

MLB 선수의 시즌·커리어 기록을 검색하고 비교하는 개인 데이터 분석 애플리케이션입니다. 외부 데이터 수집부터 검증·통계 계산·저장·시각화·로컬 AI 설명까지 하나의 흐름으로 구현했습니다.

## 핵심 기능

선수 자동완성 및 팀 필터, 즐겨찾기, 타격·투구와 고급 통계, 리그 평균, Statcast, 백분위, 통계 프로필 유사 선수, 커리어 추세, 수상, 선수 비교, MLB 리더보드와 CSV, 한국어·영어 UI를 제공합니다. 선택적으로 Ollama가 Python이 준비한 자료를 설명합니다.

## 기술 및 설계

Python, Streamlit, Plotly, requests, NumPy, pandas, SQLite를 사용합니다. UI/components, 조회/services, 계산/analytics, 설정/utils로 나누었습니다. MLB ID·시즌·범주·정규시즌을 기준으로 자료를 검증하고, 비율 통계는 원자료를 합산해 다시 계산합니다. 결측값은 임의로 채우지 않습니다.

메모리/SQLite 캐시와 조회 출처·시각을 관리하고, LOCAL 개인 저장과 CLOUD 세션 설정을 분리했습니다. AI 컨텍스트는 허용 필드 중심으로 제한합니다. pytest 회귀 테스트, 임시 DB 검증, Ruff 정적 검사와 최소 권한 GitHub Actions를 구성했습니다.

## 결과와 범위

최종 테스트 수·커버리지와 실제 연결/화면 검사 결과는 [인수인계 보고서](docs/FINAL_HANDOVER.ko.md)에 기록합니다. 원격 CI·공개 배포를 수행했다고 주장하지 않습니다. 실력 예측·보정 자료가 없는 지표·영구 다중 사용자 계정 저장소는 제공하지 않습니다. 4.9를 프로젝트 최종 버전으로 정리했습니다.

[실행 화면 및 설치법](README.md) · [구조](docs/ARCHITECTURE.md) · [통계 품질](docs/DATA_QUALITY.md)
