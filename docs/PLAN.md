# Boardy — Deep Sea Crew AI Companion

목표: "The Crew: Mission Deep Sea" (협력 트릭테이킹 보드게임)를 함께 플레이할 수 있는
AI 플레이어를 만들고, 온라인에서 친구들과 실시간으로 그 AI와 함께 플레이할 수 있는
서비스를 구축한다.

## 알려진 사실 / 가정 (검증 필요)

웹 검색으로 확인된 것:
- 2~5인용 협력 트릭테이킹 카드 게임 (전작 "Quest for Planet Nine"의 후속작)
- 색상(스위트) 카드 1~9 + 잠수함(트럼프) 카드
- 통신은 Sonar 토큰으로 카드 한 장을 공개하고 최고/최저/유일 표시
- "Currents", "Rapture of the Deep" 같은 특수 미션 심볼이 통신 제한/허용을 바꿈
- 과제 카드는 96종 (본가 박스 기준 통상 알려진 수치)

**가정하고 우선 구현한 것** (나중에 실제 룰북/카드 사진으로 교정 예정):
- 색상 4개 × 1~9 = 36장, 잠수함(트럼프) 1~4 = 4장, 총 40장
- 플레이어 3~5인 지원 (사용자 최우선 시나리오: 3인이서 4인 밸런스를 흉내내기 위해 AI 1명 참여)
- 커뮤니케이션: 게임당 1회, 카드 1장 공개 + (최고/최저/유일) 마커
- 과제(Task)는 하드코딩된 96개 실제 카드 텍스트 대신, 데이터 기반 DSL
  (`data/tasks.json`)로 절차적으로 표현. 조건 타입: `win_card`, `win_trick_number`,
  `win_exact_count`, `never_win_color`, `win_no_tricks`, `order` (순서 토큰) 등.
  실제 카드 96장 텍스트를 확보하면 `data/tasks.json`만 교체하면 됨.

이 가정들은 실제 룰북 사진/텍스트를 사용자가 제공하면 빠르게 교정 가능하도록
로직과 데이터를 분리해서 설계함.

## 단계별 계획

### Phase 1 — 규칙 엔진 (CLI) ✅ 진행 중
- `src/deepsea/cards.py`: 카드/덱
- `src/deepsea/tasks.py`: 과제 DSL + 완료 판정
- `src/deepsea/communication.py`: Sonar 토큰 통신
- `src/deepsea/state.py`: 게임 상태 (핸드, 트릭, 진행 정보)
- `src/deepsea/engine.py`: 트릭 해석, 합법수 생성, 승패 판정
- `src/deepsea/cli.py`: 사람 vs 랜덤봇 CLI 대화형 플레이
- `tests/`: pytest

### Phase 2 — AI 플레이어 학습
- The Crew는 협력 + 불완전정보(hidden hand) 게임이라 순수 AlphaZero(완전정보, 제로섬)를
  그대로 쓸 수 없음. 접근 방식:
  1. 학습 중에는 "oracle" 관점(모든 손패 공개)으로 self-play를 돌리는 Perfect-Information
     MCTS(각 시뮬레이션마다 상대 손패를 현재 정보집합과 일치하게 무작위 재배치 =
     "determinization")로 정책/가치망을 학습
  2. 실전(추론) 시에는 자신의 손패 + 공개된 통신 정보만으로 ISMCTS 수행
  3. 라이브러리: PyTorch로 직접 정책/가치망 + MCTS 구현 (범용 alpha-zero-general은
     2인 제로섬 가정이 강해 협력 게임엔 그대로 안 맞음 → 커스텀 self-play 루프 필요.
     다만 신경망 구조/학습 루프 참고용으로 조사 예정)
- 보상: 미션(과제 세트) 성공 시 +1, 실패 시 0/-1, 조기 실패 시 즉시 종료

### Phase 3 — 실시간 온라인 플레이 서비스
- 백엔드: FastAPI + WebSocket (방 생성, 좌석 배정, 턴 진행, AI 플레이어 좌석 포함)
- 프론트엔드: React (또는 간단한 SPA) — 손패, 트릭, 과제, 통신 UI
- 학습된 정책망을 백엔드에서 추론 서버로 서빙 (같은 프로세스 내 PyTorch 추론으로 충분)

## 다음 액션
Phase 1 코드 작성 중. 완료되면 `python -m deepsea.cli`로 플레이 가능.
