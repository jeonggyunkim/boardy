# Boardy AI 전략

이 문서는 "수십~수백 개 보드게임을 플레이 환경 + AI 상대/동료로 제공한다"는 목표
아래, 게임마다 AI를 어떻게 설계·학습·운용할지에 대한 결정 프레임워크다. 2026-08-10,
오목(Gomoku)과 딥씨 크루(Deep Sea Crew) 두 게임을 만들면서 나온 논의를 정리한 것 —
새 게임에 AI를 추가할 때마다 이 문서의 체크리스트부터 채우고 시작할 것.

## 핵심 전제: "게임 룰만 인터페이스에 맞춰 구현하면 알파제로가 알아서 최강 AI를 만들어준다"는
틀렸다

AlphaZero는 학습 *알고리즘*이지 모델이 아니다. 실제 신경망 구조, 상태를 벡터/텐서로
바꾸는 인코딩, 가치 함수의 의미(제로섬인지 협동인지)는 전부 게임마다 사람이 설계해야
한다. 즉 **재사용되는 건 "정답"이 아니라 "물어야 할 질문 목록"** 이다.

## 게임마다 답해야 하는 5가지 질문

| # | 질문 | 답에 따라 갈리는 것 |
|---|---|---|
| 1 | 완전정보(모두가 전체 상태를 봄)인가, 히든정보(일부만 보임)인가? | MCTS 그대로 쓸지, ISMCTS(determinization)를 쓸지, 그것도 부족하면 CFR 계열을 쓸지 |
| 2 | 히든정보라면, 상대와 **경쟁**하는 게임인가 **협동**하는 게임인가? | 경쟁이면 ISMCTS의 근본적 한계(strategy fusion)가 실전에서 발목 잡을 수 있음(→ 아래 "함정" 참고). 협동이면 그 위험은 작지만 "자기들끼리만 통하는 암구호" 위험이 대신 생김 |
| 3 | 상태가 자연스러운 2차원 격자인가, 카드/유닛 같은 이산 개체들의 집합인가? | 격자 → CNN 트렁크. 집합/평면 벡터 → MLP 트렁크(개체 수가 가변적이면 나중에 attention/GNN 검토) |
| 4 | 목표 구조가 제로섬 대결인가, 전원 협동(성공/실패 공유)인가, 개인별 점수를 겨루는 비영합인가? | 가치망 출력 형태: 제로섬 → tanh(-1~1) + 매 수마다 부호 반전 백업 / 협동 → sigmoid(0~1) 단일 공유 값 / 비영합 → 플레이어별 가치 벡터(아직 이 저장소에 사례 없음, 필요해지면 새로 설계) |
| 5 | 카드 플레이/착수 외의 부가 결정(미션 드래프트, 힌트/통신, 경매 등)도 학습 대상으로 삼을 가치가 있나? | 있다면 정책 head 추가 + 그 결정도 MCTS/self-play에 포함시켜야 함. 통신처럼 "의미가 룰로 고정된" 채널이면 의미는 고정하고 타이밍만 학습하는 식으로 스코프를 좁혀서 암구호 위험을 피할 것 |

### 지금까지의 두 사례로 본 답의 예시

| 게임 | Q1 | Q2 | Q3 | Q4 | 실제 구현 |
|---|---|---|---|---|---|
| 오목(Gomoku) | 완전정보 | 해당없음(경쟁이지만 완전정보라 ISMCTS 자체가 불필요) | 15×15 격자 | 제로섬 | CNN(10-block residual, 채널128, 319만 파라미터) + PUCT MCTS, tanh 가치, [network.py](../src/boardy/games/gomoku/network.py) / [mcts.py](../src/boardy/games/gomoku/mcts.py) |
| 딥씨 크루 | 히든정보(다른 사람 손패를 모름) | 협동 | 카드/과제 등 이산 개체 집합 | 협동(공유 성공확률) | MLP(hidden 256×3) + ISMCTS(determinization), sigmoid 가치, [network.py](../src/boardy/games/deep_sea_crew/network.py) / [mcts_inference.py](../src/boardy/games/deep_sea_crew/mcts_inference.py) |

## AI 강도 3단계 (모든 게임 공통 목표: 초보자 / 능숙한 일반인 / 인간계 최상)

구현 방식과 별개로, **탐색 예산(시뮬레이션 수)** 과 **온도(온도가 높을수록 방문횟수
분포에서 확률적으로/무작위에 가깝게 수를 뽑음)** 두 손잡이만으로 하나의 AI 구현에서
3단계를 뽑아낼 수 있다 — 게임마다 AI를 3벌 따로 만들 필요는 없다.

- 시뮬레이션 예산을 확 줄이면 "초보자스러운 실수"가 아니라 그냥 기계적으로 이상한
  수가 나올 수 있음(진짜 사람의 실수 패턴과는 다름). 지금 스코프에서는 감수할 근사치로
  보되, 나중에 "진짜 사람처럼 두는 초보자 AI"가 필요해지면 Maia Chess(실제 사람
  기보를 레이팅 구간별로 지도학습한 프로젝트) 방식처럼 별도 데이터/학습이 필요함을
  알아둘 것.
- "인간계 최상"이 실제로 나올지는 게임의 전략적 깊이에 달렸다. 오목처럼 국소 패턴
  위주 게임은 학습 없는 휴리스틱+탐색(Tier 0/1)만으로도 꽤 강할 수 있지만, 깊이가
  큰 게임은 결국 학습(Tier 2) 없이는 천장이 낮다.

## 구현 투자 3계층 (Tier) — 게임마다 어디까지 투자할지 결정

- **Tier 0 (범용, 학습 없음)**: `GameSpec`(`legal_actions`/`play`/`outcome`)만 있으면
  어떤 게임이든 즉시 동작. 순수 랜덤 롤아웃 MCTS가 여기 해당 — "value화"를 학습된
  함수가 아니라 "게임을 실제로 끝까지 무작위로 진행시켜 나온 진짜 결과"로 대신한다.
  새 게임을 등록하면 AI 관련 코드를 한 줄도 안 짜도 이 정도는 공짜로 딸려온다.
- **Tier 1 (범용 + 가벼운 탐색)**: 같은 인터페이스 위에서 사람이 짠 간단한 휴리스틱
  평가 함수를 얹은 미니맥스/MCTS. 딥러닝 이전 시대 체스 엔진들의 방식.
- **Tier 2 (게임별 맞춤, 학습)**: 위 5가지 질문에 답해서 인코딩+모델+가치망을 설계하고
  self-play로 학습. 오목/딥씨 크루가 여기 해당. 투자 비용이 크므로, "이 게임이
  플랫폼에서 얼마나 중요한가/자주 플레이되는가"를 기준으로 선별 적용할 것 — 백 개
  게임 전부에 이 투자를 할 순 없다.

## 버전 관리 & 게이트키핑 정책 (Tier 2 게임 공통)

1. **아레나 게이트키핑 필수**: 새로 학습한 candidate가 기존 최고 네트워크(incumbent)를
   실제 대국에서 이겨야만 승격. 이 검증 없이 그냥 학습만 계속 돌리면 오히려 후퇴하는
   경우가 더 많다 — 실측: 2026-08-09~10 오목 30-iteration 학습에서 22/30 iteration이
   "rejected"였음(`docs/PLAN.md` 참고). 예전에 게이트키핑 없이 15 iteration 돌렸다가
   학습 안 한 네트워크한테 진 사례도 있었음.
2. **버전 태그는 검증된 승격 시점에만**: `best.pt`(rolling SOTA 포인터) + 의미 있는
   마일스톤에만 `v1`, `v2` 같은 이름 태그. 매 iteration 체크포인트(`iter_XXXX.pt`)를
   전부 영구 보관하지 않기 — 게임 수가 늘어나면 디스크가 감당 안 됨.
3. **"학습만 더 돌리면 계속 강해진다"는 착각 주의**: 같은 모델 용량(채널/블록 수 고정)엔
   성능 천장이 있다. policy_loss/value_loss가 더 안 내려가고 arena 승률도 정체되면,
   학습을 더 돌리는 대신 모델 용량 자체를 키우는 "세대교체"를 검토할 것 — 이 경우
   이전 체크포인트 가중치를 그대로 못 이어받고 새로 학습해야 할 수 있음.
4. **어떤 게임부터 Tier 2 투자를 할지 우선순위**가 필요함 — 아직 명문화된 기준 없음
   (사용 빈도, 게임 복잡도, 인코딩 재사용 가능성 등을 기준으로 추후 정리할 것).

## 알려진 함정 (미리 알고 설계에 반영할 것)

- **경쟁형 히든정보 게임엔 ISMCTS로는 최상급이 안 나온다.** ISMCTS는 여러 "완전정보로
  가정한 상태(determinization)"를 독립적으로 탐색하고 합치는 방식인데, 이 과정에서
  "실제로는 모르는 정보를 탐색 내부적으로는 활용해버리는" 오류(strategy fusion)가
  생긴다. 포커 초인급 AI(Libratus, Pluribus)가 ISMCTS 계열이 아니라 CFR
  (Counterfactual Regret Minimization) 계열을 쓴 이유가 이것 — CFR은 "상대가 내
  전략을 다 알아도 못 뚫는 전략"을 계산하며, 일부러 예측 불가능하게 섞는 것 자체가
  최적 전략의 일부다. 경쟁 요소가 있는 히든정보 게임을 추가하게 되면 이 문서의
  Q1/Q2 답에 따라 CFR 계열을 별도 검토할 것.
- **협동형 히든정보 게임의 통신 메커니즘을 self-play로 학습시키면 "자기들끼리만 통하는
  암구호"가 생길 위험**이 있다(Hanabi AI 연구에서 잘 알려진 현상 — self-play 상대로는
  점수가 잘 나오는데 사람이나 다른 학습 에이전트와 짝지으면 급락). 딥씨 크루는 소나
  마커의 의미가 룰로 고정돼 있어 상대적으로 안전하지만, 통신/힌트를 실제로 학습
  대상에 넣을 땐 "의미는 룰대로 고정, 언제·누구에게 쓸지 타이밍만 학습"으로 스코프를
  좁힐 것.
- **PyPy는 이 스택에서 옵션이 아님**: PyTorch가 PyPI에 CPython 전용 wheel만 배포함
  (`docs/PLAN.md`의 2026-08-09 항목 참고). 순수 파이썬 로직(렌주 판정 등)이 느려도
  PyPy로 못 돌린다.
- **GPU/TPU는 self-play 구조를 "여러 게임 동시 진행 + 신경망 호출 배치화"로 다시 짜야
  실제로 이득이 있다.** 지금처럼 게임 하나·시뮬레이션 하나씩 순차 호출하는 구조에
  GPU만 붙이면 커널 실행 오버헤드가 계산량보다 커서 의미가 거의 없다. 원조
  AlphaZero/AlphaGo가 TPU를 쓴 것도 "규칙 시뮬레이션"이 아니라 오직 신경망 추론이고,
  그마저도 수천 개 self-play 게임을 병렬로 돌리며 리프 평가 요청을 모아 배치로
  처리했기 때문에 효율이 나온 것. **2026-08-11 구현**: `mcts.py`의 `run_mcts_batch`가
  여러 게임의 트리를 락스텝으로 진행시키며 매 시뮬레이션 라운드마다 리프 평가를 하나의
  forward pass로 묶고, `self_play.py`/`evaluate.py`가 이를 이용해 self-play·arena
  게임을 동시에 여러 판 돌린다.
- **위 배치화만으로는 충분하지 않았다 — 실측 프로파일링으로 확인.** "배치 self-play"를
  구현한 직후 RTX 3060에서 실제로 cProfile을 떠 보니(64게임·시뮬레이션 100회 자기대국
  배치, 2026-08-11), 신경망 forward pass는 전체 시간의 **1.1%**밖에 안 됐고, 시간의
  **65%**는 렌주 금수 판정(`board.legal_moves()`→`renju.classify_black_move`, 순수
  파이썬)이, 추가로 **19%**는 매 시뮬레이션 라운드마다 결과를 `.cpu()`로 GPU→CPU 동기화
  하는 오버헤드가 차지했다. 즉 배치화로 GPU 쪽 병목은 없앴지만, 애초에 병목은 GPU가
  아니라 CPU 순수 파이썬 로직이었던 것 — 2026-08-09 최적화 라운드(위 항목들)에서 이미
  경고했던 바로 그 문제("병목이 렌주 판정이라는 순수 파이썬 로직")가 모델을 키우고
  나서도 여전히 유효했음. 그래서 self-play/arena 게임 생성은 다시 `ProcessPoolExecutor`
  CPU 멀티프로세싱으로 돌아가되(`--self-play-workers`, 물리 코어 14개 머신에서 스윕
  테스트로 12가 안정적인 기본값 — 로지컬 코어 수 20까지 밀어붙이면 스케일링이 노이즈성
  으로 꺾임, 하이퍼스레드가 이 순수 파이썬 워크로드엔 별 도움이 안 됨), 각 워커
  프로세스 내부에서도 `run_mcts_batch`로 자기가 맡은 게임들을 배치 처리 — CPU 코어
  분산과 배치화 이득을 모두 가져감. GPU는 학습 gradient step(배치 128~256, 진짜
  matmul/conv 작업)에만 씀 — 거기서만 TF32(`torch.backends.cuda.matmul.allow_tf32`)와
  `cudnn.benchmark`도 켬. `encoding.py`의 `encode_board`도 셀당 파이썬 루프를 numpy
  벡터 연산으로 교체(작은 개선, 안전한 무료 이득).
- **CPU 병목 자체를 줄이는 건 별개의 최적화 축이고, C++로 다시 짜는 것보다 먼저 시도할
  저비용 옵션이 있다.** 위 배치화/멀티프로세싱은 "같은 총 작업량을 더 많은 코어에
  나눠서" 처리량을 올리는 것이고, `renju.py`(Renju 판정)를 Numba `@njit`로 컴파일하는
  건 "총 작업량 자체를 줄이는" 별도 축 — 둘은 곱으로 이득이 남. 2026-08-11에 적용:
  `renju.py`가 2026-08-09 라운드에서 이미 dict 대신 plain list, 언롤된 루프로 다듬어져
  있어서 Numba에 이상적인 모양이었고, `Board.cells`를 numpy 배열로 바꿔서(zero-copy로
  JIT 코드에 넘어가게) 같은 벤치마크가 1296.9초→400.4초(3.24배)로 줄어듦 — C++/Cython
  확장은 Windows 빌드 툴체인, pybind11류 바인딩, 정확성 리스크(렌주 판정은 이 프로젝트가
  반복해서 "건드리지 않는다"고 못박은 코드)까지 감수해야 하는데, Numba는 `pip install`
  만으로 그 이득의 상당 부분을 가져감 — C++는 Numba로도 부족할 때 고려할 다음 단계.
  세부 내용/정확성 검증 방법은 `docs/PLAN.md` 참고.
- **MCTS 트리를 매 수마다 새로 만들지 않고 재사용하면 이론상 이득이지만, 이 게임/설정
  에선 효과가 작다.** 실제로 둔 수의 자식 서브트리를 다음 수의 루트로 재사용하면 이미
  쌓인 visit count를 이어받아 같은 탐색 품질에 필요한 시뮬레이션이 줄어들 것으로
  기대했는데(self-play만 적용, `mcts.py`의 `BatchedMCTS`), 실측 추가 이득은 6.3%뿐
  (Numba 이후 400.4초→375.1초). 원인: 15x15 보드는 초반 합법수가 200개를 넘고
  self-play는 매 수 Dirichlet 노이즈를 섞어서 탐색을 퍼뜨리기 때문에, 시뮬레이션
  100회로는 대부분의 후보 수가 방문 1회 안팎에 그침 — 재사용해도 캐리오버되는 visit
  자체가 적다는 뜻. 구현 과정에서 두 가지를 스스로 잘못 짜서 고쳤음(처음엔 재사용
  여부와 무관하게 매번 전체 시뮬레이션을 새로 돌려서 효과가 0%였고, 그다음엔 배치
  전체를 하나의 공유 라운드 수로 묶어서 배치 내 최악의 게임에 끌려갔음) — 자세한 경위는
  `docs/PLAN.md` 참고. 교훈: "이론적으로 맞는 최적화"도 이 게임의 특성(넓은 분기 +
  탐색 노이즈)에 따라 실측 이득이 기대보다 훨씬 작을 수 있다 — 프로파일링 없이 효과를
  가정하지 말 것.

### 모델 크기 (2026-08-11 재설계)

기존엔 CPU 학습 전제로 conv 3층·64채널·non-residual(수십만 파라미터 미만)로 일부러
작게 만들었음. GPU 학습이 가능해지면서 `network.py`의 `PolicyValueNet` 기본값을
**10-block residual tower, 128채널 (실측 3,194,232 파라미터 — 이전에 여기 적혀있던
"~5M"은 최종 구조 확정 전 추정치였고 부정확했음, 2026-08-12 `sum(p.numel() for p in
net.parameters())`로 재확인)**로 교체 — `channels`/`num_blocks`
생성자 인자로 계속 조절 가능하게 남겨둠(작은 보드용 빠른 테스트, 추후 재조정 대비).
15x15 렌주는 바둑보다 훨씬 단순한 게임이라 이 정도 용량 + 충분한 MCTS 시뮬레이션
조합이면 인간 최상급을 넘어서기에 충분할 것으로 예상 — 다만 실측 검증은 아직임(아래
Elo 래더 섹션 참고). 체크포인트 포맷도 `{"config": {...}, "state_dict": ...}`로 바뀌어서
(`save_checkpoint`/`load_checkpoint`), 나중에 아키텍처를 또 바꿔도 로더가 잘못된
모양의 네트워크를 조용히 만들어버리는 일이 없음. 기존 체크포인트는 이 포맷과 호환 안
됨(로드 시 명시적으로 예외 발생) — 어차피 로컬에 남아있던 체크포인트가 없어서 마이그
레이션 이슈는 없었음.

### Elo 래더 (실력 평가 개선, 2026-08-11)

기존엔 `RandomPlayer` 상대 승률만 측정해서 "인간보다 강함"을 뒷받침하기엔 부족했음.
`elo.py`에 표준 Elo 갱신식(K=32)을 추가하고, `train.py`가 매 iteration의
candidate-vs-incumbent 아레나 결과로 레이팅을 갱신해 `checkpoints_gomoku/
elo_ratings.json`에 iteration별 이력을 남김. **candidate(`net`)와 best(`best_net`)
레이팅은 따로 관리**(2026-08-11) — candidate는 reject돼도 더 이상 리셋 안 되고 계속
이어서 학습되므로(아래 "학습 결과" 항목의 옵티마이저 버그 참고), 둘이 항상 같은
레이팅에서 출발한다고 가정하면 여러 iteration 연속 rejected될수록 부정확해짐. 옛
포맷(`current` 키 하나)도 자동 마이그레이션. **주의**: 이 레이팅은 이 프로젝트의
체크포인트끼리 상대 비교용이고, 사람이나 외부 엔진의 Elo 풀과 보정된 값이 아님 —
"이전 세대보다 얼마나 강해졌는가"를 추세로 보는 용도. 두 체크포인트를 직접 붙여보고
싶으면 `gomoku-eval --checkpoint A.pt --vs-checkpoint B.pt`로 1회성 추정치를 볼 수
있음(역시 같은 이유로 비보정 추정치).

## 열린 TODO

- 딥씨 크루 미션 드래프트/통신을 학습 대상으로 확장할지 결정 (지금은 완전 무작위,
  `players.py`의 `choose_task`/`choose_communication` 참고)
- Tier 0(범용 랜덤 롤아웃 MCTS)을 실제로 구현해서 모든 등록 게임에 기본 AI로 제공
- ~~GPU 배치 self-play 리팩터링~~ — 완료 (2026-08-11, 위 "GPU/TPU" 항목 참고). 남은 건
  실제 GPU 학습 런을 돌려서 새 10-block/128ch 네트워크 + Elo 래더로 세대 간 실질적
  강도 향상이 나타나는지 확인하는 것.
- 난이도 3단계(시뮬레이션 수/온도 매핑)를 게임별로 실제 프리셋 값으로 확정
- 게임별 Tier 2 투자 우선순위 기준 수립
- 체크포인트 보존 정책 구체화 (마일스톤만 남기고 나머지 정리하는 스크립트/규칙)

## 참고 도서/논문

RL·게임 AI는 단일 교과서 하나로 다 안 커버돼서, 기초 교과서 + 이정표 논문들을
같이 봐야 한다. 아래는 이번 논의에서 나온 주제(MCTS, AlphaZero, 히든정보, CFR/포커,
협동 멀티에이전트)를 실제로 다루는, 존재가 확실한 자료들이다.

- **기초 교과서**: Richard S. Sutton & Andrew G. Barto, *Reinforcement Learning: An
  Introduction* (2nd ed., 2018). RL 전체의 표준 교과서. 저자들이 PDF를 무료로
  공개함(http://incompleteideas.net/book/the-book-2nd.html). 정책/가치 함수, TD학습,
  MCTS 등 이 프로젝트에서 쓰는 개념들의 이론적 기반.
- **MCTS 자체를 깊게**: Cameron B. Browne et al., "A Survey of Monte Carlo Tree
  Search Methods" (*IEEE Transactions on Computational Intelligence and AI in
  Games*, 2012). 책은 아니고 서베이 논문이지만, MCTS의 변형/이론을 가장 폭넓게
  정리한 표준 레퍼런스로 자주 인용됨.
- **실전/코드 위주로 감 잡기**: Maxim Lapan, *Deep Reinforcement Learning Hands-On*
  (2nd ed., Packt). Connect4류 게임에 AlphaZero 스타일(정책/가치망 + MCTS self-play)을
  직접 구현하는 장이 있어서, 지금 이 저장소가 하고 있는 작업과 가장 결이 비슷함.
- **멀티에이전트/게임이론 기초**: Yoav Shoham & Kevin Leyton-Brown, *Multiagent
  Systems: Algorithmic, Game-Theoretic, and Logical Foundations* (2008). 저자들이
  무료 공개(http://www.masfoundations.org/). 내시 균형, 정보집합, 제로섬/비영합 등
  CFR을 이해하기 전에 필요한 게임이론 용어들을 여기서 잡을 수 있음.
- **불완전정보/포커(CFR 계열)**: 단일 대중서보다 원 논문들이 표준임.
  - Martin Zinkevich et al., "Regret Minimization in Games with Incomplete
    Information" (NeurIPS 2007) — CFR을 처음 제시한 논문.
  - Noam Brown & Tuomas Sandholm, "Superhuman AI for heads-up no-limit poker:
    Libratus beats top professionals" (*Science*, 2018).
  - Noam Brown & Tuomas Sandholm, "Superhuman AI for multiplayer poker"
    (*Science*, 2019, Pluribus) — 6인 포커까지 확장한 사례.
- **AlphaGo/AlphaZero/MuZero 원 논문 (알고리즘의 1차 출처)**:
  - David Silver et al., "Mastering the game of Go with deep neural networks and
    tree search" (*Nature*, 2016, AlphaGo).
  - David Silver et al., "Mastering the game of Go without human knowledge"
    (*Nature*, 2017, AlphaGo Zero).
  - David Silver et al., "A general reinforcement learning algorithm that
    masters chess, shogi, and Go through self-play" (*Science*, 2018, AlphaZero).
  - Julian Schrittwieser et al., "Mastering Atari, Go, chess and shogi by
    planning with a learned model" (*Nature*, 2020, MuZero) — "완벽한 규칙
    시뮬레이터가 있어야 한다"는 전제 자체를 없앤 후속작.
- **협동 히든정보(딥씨 크루와 가장 가까운 문제)**: Nolan Bard et al., "The Hanabi
  Challenge: A New Frontier for AI Research" (*Artificial Intelligence*, 2020).
  self-play 에이전트가 "자기들끼리만 통하는 암구호"를 만들어버리는 문제(ad-hoc
  teamplay)를 정면으로 다룬 논문 — 딥씨 크루 통신 메커니즘을 학습시키기 전에 꼭
  읽어볼 것.
