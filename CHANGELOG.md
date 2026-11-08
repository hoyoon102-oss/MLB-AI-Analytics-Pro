# Changelog

## 4.9 Final — 프로젝트 인수인계

- 부분 실패한 시즌 이력/커리어가 영구 캐시에 저장되거나 재사용되는 오류 수정.
- 캐시의 원시 컨테이너/NaN/무한대 검증 및 회귀 테스트 3개 추가.
- 기존 미사용 import 23개 정리, Ruff 검사와 CI 단계 추가.
- 실제 MLB/선수 검색/하루 Statcast/Ollama 연결과 Windows 런처 재검증.
- 현재 4.9 UI의 1440/390px 오프라인 스크린샷 및 브라우저 검사 추가.
- README 재정리, PROJECT_SUMMARY 및 최종 인수인계/체크포인트 목록 준비.
- 기존 기능·개인 데이터·start.bat·테마 유지. 태그/원격 공개는 승인 대기.

## 4.9 — QA & Deployment Preparation

- 기존 unittest를 pytest로 실행하고 임시 개인 저장소/오프라인 차단 및 커버리지 측정 추가.
- 최소 권한 GitHub Actions CI 추가. 배포 단계 없음.
- LOCAL/CLOUD 환경 분리. CLOUD 개인 설정은 세션 전용, SQLite/Ollama 차단.
- 손상 캐시 형식 검증과 잘못된 TTL 설정 복구.
- 통계 계산/배포 경계/클라우드 UI 테스트와 오프라인 분석 성능 측정 추가.
- 보안·구조·테스트·데이터 출처·배포 준비도 문서 추가.
- 기존 통계 공식, 개인 데이터, start.bat, 네이비 테마 유지.

4.8 이하의 기존 변경 기록은 docs/V48_REPORT.ko.md 및 이전 버전 보고서에 보존합니다.
