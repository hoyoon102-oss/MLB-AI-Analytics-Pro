# 배포 준비 평가 (배포하지 않음)

추천 순서: Windows LOCAL을 계속 사용하고, 공개 필요가 확정되면 AI 없이 CLOUD 데모를 별도로 검증합니다. 장기 다중 사용자 서비스는 인증·사용자별 저장소·운영 백업·요청량 제한이 필요합니다. 현재 정식 공개 서비스 준비 완료 상태가 아닙니다.

| 환경 | 평가 |
|---|---|
| Windows LOCAL | 기존 start.bat 및 JSON/SQLite/Ollama 유지. 로컬 테스트 증거는 RELEASE_READINESS 참고 |
| Streamlit Community Cloud | app.py, requirements.txt, 기존 테마 사용. CLOUD 필수. SQLite/개인 파일 영구 저장/로컬 AI 지원 안 함 |
| Python 호스팅/컨테이너 | Linux 설치와 자원 검증 필요. 영구 디스크는 공용 파일 저장 문제를 해결하지 않음. 다중 사용자 저장 설계 별도 필요 |

설정은 환경변수입니다. .env.example은 안내용이며 자동 로드하지 않습니다.

```powershell
$env:MLB_ANALYTICS_MODE="LOCAL"
.\start.bat
# 별도 데모 검증 세션에서만:
$env:MLB_ANALYTICS_MODE="CLOUD"
.\.venv-test\Scripts\python.exe -m streamlit run app.py
```

CLOUD는 Ollama/관리자 DB 기능을 차단하고 개인 설정을 세션에만 저장합니다. localhost:11434는 방문자 컴퓨터가 아닙니다. 미래 AI 후보는 인증된 사설 추론 서버나 호스팅 내 전용 서비스이며 이번 버전에는 연결하지 않았습니다.

Python 3.11을 CI/향후 호스팅 기준으로 선택했습니다. 실제 로컬 증거는 Python 3.10.4이며 Linux/3.11 실행은 CI가 실제 동작하기 전까지 NOT TESTED입니다. 의존성은 기존 범위를 유지하며 무조건 최신화하지 않았습니다. pybaseball은 실제 import가 없어 추가하지 않았습니다. Playwright는 개발 의존성입니다.

[Streamlit 의존성 안내](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies)와 [Python 설정 안내](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy)를 확인했습니다. [공식 저장소 안내](https://docs.streamlit.io/develop/concepts/connections/connecting-to-data)에 따라 로컬 파일 지속성을 가정하지 않습니다.

MLB/Savant 외부 HTTPS가 필요합니다. Statcast는 버튼 기반/기간 분할/제한된 응답 크기를 유지합니다. 공개 트래픽에 대한 동시 요청 제한, 실측 메모리 상한, 부하 시험은 아직 없습니다. 예측 메모리 요구량을 만들어 내지 않았습니다. 실제 공개 전 소규모 Linux staging 측정과 출처 사용 조건 검토가 필요합니다.

GitHub: 저장소 설명 제안은 “Bilingual Streamlit MLB analytics with verified statistics, local SQLite cache, and optional local Ollama reports.”입니다. Git 설치 후 로컬 초기화, 추적 목록 검토, 비공개 원격 연결을 직접 진행하세요. 자동 push/저장소 생성/배포 workflow는 없습니다. 라이선스는 소유자와 선택 전까지 추가하지 않았습니다.
