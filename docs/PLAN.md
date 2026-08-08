# Boardy — 보드게임 AI 컴패니언

목표: 여러 보드게임을 함께 플레이하는 AI 플레이어를 만들고, 온라인에서 친구들과
실시간으로 그 AI와 함께 플레이할 수 있는 서비스를 구축한다. 첫 게임은 협력
트릭테이킹 카드게임 "The Crew: Mission Deep Sea" (저장소 내 슬러그: `deep_sea_crew`).

## 저장소 구조 (2026-08-08 리팩터링)

처음엔 `deep_sea_crew` 하나만 구현하면서 시작했지만, 이 저장소의 실제 목적은 여러
보드게임을 지원하는 것이라 구조를 다음과 같이 나눴다:

```
src/boardy/
  core/
    game_spec.py   게임이 구현해야 하는 최소 계약 (GameSpec dataclass)
    registry.py    슬러그 -> GameSpec 레지스트리 (게임 패키지를 import하면 등록됨)
  web/             게임에 무관한 공용 실시간 서비스 (FastAPI + WebSocket)
    rooms.py       Room이 GameSpec을 통해서만 게임 상태를 다룸 (카드/트릭 개념 모름)
    server.py      REST(`/api/rooms`, `/api/games`) + WS(`/ws/{code}`)
    static/        지금은 Deep Sea Crew 전용 프론트엔드 (아래 설명 참고)
  cli.py           `python -m boardy.cli --game <slug> ...` — 게임별 CLI에 위임
  games/
    deep_sea_crew/ 이 게임의 규칙 엔진 + AI 학습 파이프라인 + 자체 CLI 전부
      spec.py      engine.py 등을 GameSpec으로 감싸서 registry에 등록
      web_view.py  GameState -> 웹 프론트엔드가 기대하는 JSON 스키마 매핑
data/deep_sea_crew/tasks.json   이 게임의 과제 데이터 (placeholder, 아래 참고)
tests/deep_sea_crew/            이 게임의 테스트
```

**설계 원칙**: 트릭테이킹 게임의 카드/트릭/통신 같은 개념은 다른 장르 게임(예: 체스류)과
공유할 게 거의 없다. 그래서 게임 엔진·AI·상태 표현은 게임마다 완전히 독립적으로 두고,
`boardy.web`/`boardy.cli` 같은 호스트 레이어가 실제로 필요로 하는 좁은 경계만
`GameSpec`으로 표준화했다: 새 게임을 시작, 좌석별 합법수 조회, 액션 적용, 차례/종료
조회, 좌석별 JSON 뷰 렌더링. 액션은 항상 문자열이라(카드 코드 등) 내부 액션 타입이
무엇이든 경계가 단순하게 유지된다. 프론트엔드(`static/`)는 아직 Deep Sea Crew 전용
UI지만, 그 응답 스키마(hand/legal_moves/trick_in_progress/tasks/...)는 "손패 형태의
토큰 + 목표 목록" 형태의 다른 카드게임이라면 상당 부분 재사용 가능하도록 잡아뒀다 —
체스처럼 완전히 다른 형태의 게임엔 안 맞고, 그건 그때 가서 별도 프론트엔드가 필요함.

새 게임 추가 방법: `src/boardy/games/<slug>/`에 규칙 엔진 구현 → `spec.py`에서
`GameSpec`으로 감싸 `register()` 호출 → `games/__init__.py`에서 import 한 줄 추가.

## 알려진 사실 / 가정 (Deep Sea Crew, 검증 필요)

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
  (`data/deep_sea_crew/tasks.json`)로 절차적으로 표현. 조건 타입: `win_card`,
  `win_trick_number`, `win_exact_count`, `never_win_color`, `win_no_tricks` 등.
  실제 카드 96장 텍스트를 확보하면 이 파일만 교체하면 됨.

이 가정들은 실제 룰북 사진/텍스트를 사용자가 제공하면 빠르게 교정 가능하도록
로직과 데이터를 분리해서 설계함.

## 단계별 계획 (Deep Sea Crew 기준)

### Phase 1 — 규칙 엔진 (CLI) ✅ 완료
- `src/boardy/games/deep_sea_crew/cards.py`: 카드/덱
- `.../tasks.py`: 과제 DSL + 완료 판정
- `.../communication.py`: Sonar 토큰 통신
- `.../engine.py`: 게임 상태, 트릭 해석, 합법수 생성, 승패 판정
- `.../missions.py`: `data/deep_sea_crew/tasks.json` 템플릿으로 실제 미션 생성
- `.../cli.py`: 사람 vs 랜덤봇 CLI 대화형 플레이
- `tests/deep_sea_crew/`: pytest (20개 통과)

### Phase 2 — AI 플레이어 학습 ✅ 파이프라인 완료, 학습 신호는 아직 미검증
채택한 구조:
1. **학습**: `mcts.py`의 `run_mcts`가 실제(oracle) `GameState` 위에서 표준 PUCT 탐색을 돈다 —
   협력 + 순차턴(한 번에 한 명만 행동) 게임이라 제로섬 minimax의 부호 반전이 필요 없고,
   그냥 공유 스칼라 가치(미션 성공 확률)를 트리 위로 그대로 backup하는 단일 에이전트
   MCTS로 축소됨. 신경망은 노드마다 항상 "행동할 좌석 하나의" 부분정보 인코딩만 보고
   정책/가치를 예측하므로, 탐색 자체는 치팅해도 신경망은 은닉정보 없이 일반화하도록 학습됨.
2. **실전 추론**: `mcts_inference.py`의 `run_ismcts`가 여러 개의 "determinization"
   (공개 정보 — 지금까지 낸 카드, 트릭 위 카드, 공개된 Sonar 신호, 그리고 트릭 규칙상
   특정 색을 안 따라간 사람은 그 색이 없다는 표준 추론)에 부합하는 손패 배치를 무작위로
   샘플링해 각각에 대해 `run_mcts`를 돌리고, 루트의 방문 횟수를 모아 최종 정책으로 사용.
3. 구현체: `encoding.py`(자기중심 특징 인코딩), `network.py`(PyTorch MLP, 정책 헤드
   40장 카드 + 가치 헤드 시그모이드), `self_play.py`, `train.py`(자기대국 → 리플레이
   버퍼 → 학습 → 체크포인트 저장 루프), `evaluate.py`(RandomPlayer 대비 미션 성공률
   비교).
- 범용 alpha-zero-general 라이브러리는 2인 제로섬/완전정보 가정이 강해 그대로 못 쓰고,
  위 구조를 직접 구현함 (체스/바둑/오델로류 완전정보 게임엔 적합하지만 이 프로젝트엔 부적합).
- 보상: 미션(과제 세트) 전원 성공 시 1.0, 하나라도 실패 시 0.0 (팀 공유 가치).
- **1차 검증 결과 (2026-08-08)**: 3인/난이도6, 15 iteration × iteration당 15게임 ×
  시뮬레이션 25회짜리 스모크 학습을 CPU로 돌려봄 (`checkpoints/`, gitignore됨).
  가치망 손실(value_loss)은 0.5→0.02대로 잘 떨어졌지만, 이건 대부분 "거의 항상 실패"라는
  패턴을 외운 것에 가까움 — 정책 손실(policy_loss)은 거의 안 줄었고, 학습된 AI(ISMCTS
  탐색 포함)의 실제 성공률도 6.7%로 랜덤(3.3%)과 표본 30게임 기준 통계적으로 구분 안 됨.
  파이프라인 자체(자기대국→학습→체크포인트→ISMCTS 추론→평가)는 끝까지 정상 동작 확인.
- **2차 검증 결과 — 쉬운 난이도 대조 실험 (2026-08-08)**: 난이도를 1로 낮춰서(랜덤
  플레이어 기준 성공률 ≈23%, 난이도6의 ≈1.5%보다 훨씬 관측하기 쉬움) 20 iteration ×
  게임 20개 × 시뮬레이션 30회로 재학습(`checkpoints_easy/`, gitignore됨) 후, 학습
  효과와 탐색(search) 효과를 분리하기 위해 4가지를 비교:
  | 조건 | 성공률 |
  |---|---|
  | 랜덤 플레이어만 | 18~26% (n=60~100) |
  | 학습망, 탐색 없이 그리디 정책만 | 23% — 랜덤과 구분 안 됨 |
  | **학습 안 된** 신경망 + ISMCTS 탐색 | 31.7% (n=60) |
  | **학습된** 신경망 + ISMCTS 탐색 | 26.7% (n=60) |

  **결론**: 탐색(MCTS/ISMCTS) 자체는 확실히 유효함 — 학습 안 된 랜덤 초기화 망을 붙여도
  탐색만으로 랜덤 대비 성공률이 오름. 반면 신경망이 자기대국 학습으로 뭔가 유용한 걸
  배웠다는 증거는 아직 없음 (학습된 쪽이 오히려 조금 낮게 나왔지만 n=60이라 오차범위 안).
- **3차 시도 — 대규모 재학습 (2026-08-08, 중단됨)**: 60 iteration × 게임 30개 ×
  시뮬레이션 50회(3단계로 나눠 진행 예정, 총 2.5시간 추정) 학습을 시작했으나, 사용자가
  이 시점에 저장소를 다중 게임 구조로 리팩터링해달라고 요청. 모듈 경로가 바뀌는 리팩터링과
  충돌할 게 뻔해서(재개 시 어차피 새 경로로 다시 실행해야 함) 초반(iteration 1개 완료
  전)에 중단하고 리팩터링을 먼저 진행함. **리팩터링 이후 재개 필요** — 명령어는
  `python -m boardy.games.deep_sea_crew.train ...`로 바뀜, `checkpoints_big/`은
  비어있거나 미완성 상태.
- **다음에 학습을 재개한다면**: (a) 위 대규모 학습을 새 경로로 재시작, (b) 신경망
  크기·러닝레이트 등 하이퍼파라미터 튜닝, (c) GPU 사용 여부 검토, (d) 자기대국 시뮬레이션
  수 자체를 늘려 학습 타겟(정책 분포) 품질을 높이는 것도 고려.

### Phase 3 — 실시간 온라인 플레이 서비스 ✅ 뼈대 완료 (+ 다중 게임 호스팅으로 일반화)
- `src/boardy/web/rooms.py`: 인메모리 Room/좌석 관리. **GameSpec을 통해서만** 게임 상태를
  다루므로 카드/트릭 같은 개념을 전혀 모름 — 다른 게임이 등록되면 그대로 호스팅 가능.
  사람=WebSocket, AI=`spec.make_random_player`/`make_smart_player`. 단일 프로세스 전제,
  재연결/영속화는 아직 없음 — 스켈레톤 단계라 의도적으로 단순하게 둠.
- `src/boardy/web/server.py`: FastAPI. `GET /api/games`로 등록된 게임 목록, `POST
  /api/rooms`로 (게임 슬러그 지정해) 방 생성, `/ws/{code}` WebSocket으로
  join/add_ai/start/play/communicate 메시지 처리 (액션 페이로드 키는 게임 무관하게
  `action`). AI 차례는 서버가 자동 처리.
- `src/boardy/games/deep_sea_crew/web_view.py`: `GameState` -> 웹이 기대하는 JSON
  스키마로 매핑 (이 파일이 GameSpec.serialize_seat 구현체 — 게임별 지식이 여기 있음).
- `src/boardy/web/static/`: React 대신 순수 HTML/CSS/JS 스켈레톤 (npm 툴체인 없이 바로
  구동 가능하게 하려는 선택). 지금은 Deep Sea Crew 전용 UI (카드 코드/색상 렌더링 등).
- `src/boardy/games/deep_sea_crew/ai.py`: AI 좌석용 공유 `PolicyValueNet` 싱글턴
  (checkpoints_easy/ → checkpoints/ 순으로 체크포인트 탐색, 없으면 학습 안 된 망으로
  폴백 — 위 대조실험대로 탐색 자체가 랜덤보다 강하므로 이래도 의미 있음). 로비에서 AI
  추가 시 랜덤/스마트(탐색) 선택 가능. 스마트 AI의 ISMCTS 탐색은
  `loop.run_in_executor`로 돌려 다른 연결을 막지 않도록 함.
- 브라우저로 방 생성 → AI 2석 채움(랜덤+스마트 혼합) → 게임 시작 → 합법수만 클릭 가능 →
  AI 턴 자동 진행 → Sonar 통신 → 미션 종료 배너까지, 리팩터링 이후 구조로 전체 플로우
  재검증 완료 (2026-08-08).
- **아직 안 한 것**: 재연결/방 목록/영속 저장소, 모바일 반응형, React 전환 여부 결정.
  (2026-08-08 업데이트: 프론트엔드 게임 선택 UI는 Gomoku 추가하면서 같이 구현함 — 아래
  Phase 4 참고.)

## Phase 4 — Gomoku (두 번째 게임): 진짜 AlphaZero ✅ 완료, 학습은 진행 중

Deep Sea Crew는 협력+불완전정보라 AlphaZero를 억지로 변형해서 썼지만, Gomoku(오목)는
정반대로 골랐다 — 진짜 2인 제로섬 완전정보 게임이라 표준 AlphaZero 자기대국이 그대로
들어맞는지, 그리고 `GameSpec` 경계가 완전히 다른 종류의 게임에도 실제로 잘 작동하는지
검증하는 목적.

- `board.py`/`engine.py`: 9×9 보드, 5개 연속이면 승리 (Renju식 흑 금수 없음). 15×15/19×19
  대신 9×9를 고른 건 CPU로 실제 학습이 끝나는 규모여야 해서.
- `network.py`: 작은 CNN (conv 3블록 + 정책/가치 헤드), 입력 평면 4장(내 돌, 상대 돌,
  마지막 수, 흑/백 차례 표시).
- `mcts.py`: 진짜 2인 제로섬 PUCT — 각 노드의 평균 가치는 "그 노드에서 둘 차례인
  사람" 관점으로 저장되고, 한 수 위로 backup할 때마다 부호가 반전됨(`value = -value`).
  그래서 자식 선택 시 점수는 `-child.value`를 씀 (자식의 가치는 부모 입장에서 보면
  상대方 관점이므로). 4목이 완성된 상황을 일부러 만들어서 탐색이 승리 완성수를
  실제로 찾아내는지 테스트로 검증함.
- `self_play.py`/`train.py`/`evaluate.py`: Deep Sea Crew와 같은 자기대국→리플레이
  버퍼→학습→체크포인트 구조지만, 가치 타깃이 게임 전체에서 하나가 아니라 수마다
  부호가 바뀜(그 수를 둔 사람 기준 +1/-1/0).
- `cli.py`: 사람 vs 랜덤/학습망 터미널 플레이, ASCII 보드.
- `spec.py`/`web_view.py`: GameSpec 등록 + 웹 프론트엔드용 board-grid JSON 스키마.

**웹 프론트엔드 일반화**: 기존엔 Deep Sea Crew 전용이던 `static/`을 게임별로 다른
렌더러를 쓰도록 고침 — 방 생성 시 `GET /api/games`로 채워지는 게임 선택 드롭다운 추가,
서버가 모든 `state` 메시지에 게임 슬러그를 포함시키고, `app.js`가 슬러그로 렌더러를
분기(카드 손패 뷰 vs 클릭 가능한 NxN 격자 뷰). 브라우저에서 두 게임 다 방 생성→AI
채움→플레이→종료 배너까지 실제 검증 완료.

**GameSpec 변경**: `Player.choose_card` 메서드명을 `choose_action`으로 바꿈 — 원래
"choose_card"는 카드게임 전용 이름이 범용 프로토콜에 잘못 남아있던 것.

### 학습 결과 — gatekeeping의 중요성을 직접 발견함 (2026-08-08)

1차: 15 iteration × 게임 25개 × 시뮬레이션 100회, gatekeeping 없이(매 iteration 무조건
최신 가중치 승격) 학습. `policy_loss`가 4.14→3.18로 꾸준히 줄어서(균등분포 기준선
ln(81)≈4.39) 학습 자체는 되고 있었음. 랜덤 상대로는 학습망/학습안된망 둘 다 95%
승률(38/40) — 오목은 탐색 자체가 워낙 강해서 랜덤 상대로는 천장 효과가 남.

**진짜 비교는 학습망 vs 학습안된망 직접 대결**(탐색 80회, 온도 0.5로 실제 확률적
독립 대국 30판): **학습망 9승 — 학습안된망 21승**. 학습된 쪽이 통계적으로 유의하게
더 약했음(이 정도로 치우칠 확률 ≈1.5%, 우연이 아님).

**원인**: 학습안된 망은 사실상 균등분포 prior라 PUCT 탐색이 넓게 퍼지고, 오목은 탐색
중 실제 승패가 정확히 확인되는 게임이라 이것만으로도 충분히 강함. 반면 15 iteration
(자기대국 375판)짜리 학습망은 "애매하게 확신에 찬" prior를 갖게 됐는데, 그 확신이
아직 정확하지 않아서 오히려 얕은 탐색 예산에서 탐색을 나쁜 방향으로 좁힘. 더 근본적인
원인은 **gatekeeping 부재** — 매 iteration마다 무조건 승격시키다 보니 일시적 후퇴를
감지·차단할 방법이 없었음. 원조 AlphaZero 논문도 정확히 이 문제 때문에 "새 망이 기존
최강 망을 실전에서 과반 이상 이겨야만 승격" 하는 평가 단계를 둠.

**수정**: `evaluate.arena(candidate, incumbent, ...)` 추가, `train.py`가 이제
`best.pt`(gatekeeping 통과한 망, 자기대국에도 이걸 씀) vs 후보(`net`, 매 iteration
학습됨)를 매번 12판 아레나 대국으로 겨루게 하고, 후보가 이겨야만(승수>패수) 승격,
아니면 후보를 `best.pt`로 리셋. `ai.py`도 `best.pt`를 우선 사용하도록 변경.
기존(gatekeeping 없이 학습된) 체크포인트는 위 실험대로 학습 안 된 것보다 못하다는 게
증명됐으므로 `checkpoints_gomoku/`를 비우고 gatekeeping 파이프라인으로 처음부터 재학습.

**2차 (진행 중)**: 80 iteration × 게임 25개 × 시뮬레이션 100회, 아레나 12판×시뮬레이션
80회, gatekeeping 포함. 백그라운드로 실행 중 (예상 소요 ~6-7시간). 완료되면 승격률과
최종 head-to-head 결과를 여기 기록 예정.

## 다음 액션
Phase 1~4 모두 동작. Gomoku 대규모 gatekeeping 학습이 백그라운드에서 진행 중 (완료되면
결과 기록). 그 외 선택지: (a) Deep Sea Crew도 gatekeeping을 도입해서 대규모 재학습,
(b) 실제 룰북 확보해 `data/deep_sea_crew/tasks.json`을 진짜 96장 과제로 교체,
(c) 웹 UI/UX 다듬기 (재연결, 방 목록, React 전환 등).
