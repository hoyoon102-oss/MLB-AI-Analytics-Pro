# 구조와 저장소

`app.py` → `components/dashboard.py`가 화면을 조립합니다. `components`는 UI, `services`는 외부 조회/SQLite, `analytics`는 계산, `utils`는 설정/번역/개인 저장, `translations`는 한영 사전입니다. 전체 import 목록은 `.backups/v49-import-inventory.json`에 있습니다.

LOCAL: Streamlit 메모리 캐시 → SQLite 캐시 → MLB/Savant 조회. SQLite는 datasets(캐시 키 PK), players(MLB ID PK), teams(팀 ID+시즌 복합 PK), user_version=1을 사용합니다. datasets는 일부 데이터셋만 보관하므로 players와 외래키 관계는 없습니다. 연결마다 foreign_keys=ON, DELETE journal, timeout=10초를 적용합니다. 미래 스키마는 거부합니다. JSON 개인 파일은 기존 data 폴더에 남습니다.

CLOUD: 개인 JSON 읽기/쓰기를 우회하고 Streamlit session_state를 사용합니다. SQLite 접근과 Ollama를 차단합니다. 공개 통계 메모리 캐시는 프로세스 내 공유 가능하지만 즐겨찾기/언어/프리셋은 공유하지 않습니다. 브라우저 재연결이나 서버 재시작 시 세션 설정은 사라질 수 있습니다. 기존 개인 정보를 자동 이관하지 않습니다.
