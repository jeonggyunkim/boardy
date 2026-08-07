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

### Phase 1 — 규칙 엔진 (CLI) ✅ 완료
- `src/deepsea/cards.py`: 카드/덱
- `src/deepsea/tasks.py`: 과제 DSL + 완료 판정
- `src/deepsea/communication.py`: Sonar 토큰 통신
- `src/deepsea/engine.py`: 게임 상태, 트릭 해석, 합법수 생성, 승패 판정
- `src/deepsea/missions.py`: `data/tasks.json` 템플릿으로 실제 미션(과제 목록) 생성
- `src/deepsea/cli.py`: 사람 vs 랜덤봇 CLI 대화형 플레이
- `tests/`: pytest (20개 통과)

### Phase 2 — AI 플레이어 학습 ✅ 파이프라인 완료, 학습 진행 중
채택한 구조 (제안대로 진행):
1. **학습**: `mcts.py`의 `run_mcts`가 실제(oracle) `GameState` 위에서 표준 PUCT 탐색을 돈다 —
   협력 + 순차턴(한 번에 한 명만 행동) 게임이라 제로섬 minimax의 부호 반전이 필요 없고,
   그냥 공유 스칼라 가치(미션 성공 확률)를 트리 위로 그대로 backup하는 단일 에이전트
   MCTS로 축소됨. 신경망은 노드마다 항상 "행동할 좌석 하나의" 부분정보 인코딩만 보고
   정책/가치를 예측하므로, 탐색 자체는 치팅해도 신경망은 은닉정보 없이 일반화하도록 학습됨.
2. **실전 추론**: `mcts_inference.py`의 `run_ismcts`가 여러 개의 "determinization"
   (공개 정보 — 지금까지 낸 카드, 트릭 위 카드, 공개된 Sonar 신호, 그리고 트릭 규칙상
   특정 색을 안 따라간 사람은 그 색이 없다는 표준 추론)에 부합하는 손패 배치를 무작위로
   샘플링해 각각에 대해 `run_mcts`를 돌리고, 루트의 방문 횟수를 모아 최종 정책으로 사용.
3. 구현체: `src/deepsea/encoding.py`(자기중심 특징 인코딩), `network.py`(PyTorch MLP,
   정책 헤드 40장 카드 + 가치 헤드 시그모이드), `self_play.py`, `train.py`(자기대국 →
   리플레이 버퍼 → 학습 → 체크포인트 저장 루프), `evaluate.py`(RandomPlayer 대비 미션
   성공률 비교).
- 범용 alpha-zero-general 라이브러리는 2인 제로섬/완전정보 가정이 강해 그대로 못 쓰고,
  위 구조를 직접 구현함 (체스/바둑/오델로류 완전정보 게임엔 적합하지만 이 프로젝트엔 부적합).
- 보상: 미션(과제 세트) 전원 성공 시 1.0, 하나라도 실패 시 0.0 (팀 공유 가치).
- 다음 확인할 것: 학습이 실제로 RandomPlayer 대비 성공률을 유의미하게 끌어올리는지
  (`deepsea-eval`로 검증), 이후 반복 횟수/시뮬레이션 수를 늘려 본격 학습.

### Phase 3 — 실시간 온라인 플레이 서비스
- 백엔드: FastAPI + WebSocket (방 생성, 좌석 배정, 턴 진행, AI 플레이어 좌석 포함)
- 프론트엔드: React (또는 간단한 SPA) — 손패, 트릭, 과제, 통신 UI
- 학습된 정책망을 백엔드에서 추론 서버로 서빙 (같은 프로세스 내 PyTorch 추론으로 충분)

## 다음 액션
Phase 1 코드 작성 중. 완료되면 `python -m deepsea.cli`로 플레이 가능.
