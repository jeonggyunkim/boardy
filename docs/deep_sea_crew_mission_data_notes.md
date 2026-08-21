# Deep Sea Crew — 미션 카드 데이터 출처 및 확인 필요 항목

`data/deep_sea_crew/tasks.json`의 96장은 두 출처를 조합해서 만들어졌다:

1. 사용자가 실제 카드를 보고 직접 옮겨 적은 한국어 텍스트 (1차 자료, 실물 카드 기준)
2. 인터넷에서 찾은 영어 버전 미션 리스트 (2차 자료, 대조용으로 사용)

두 자료를 96장 전부 대조한 결과 불일치가 2건 발견되어 영어 자료 쪽을 채택해 반영했다.
다만 이 영어 자료도 100% 정확하다는 보장은 없으므로, 아래 항목들은 **실물 카드를
직접 보고 다시 확인이 필요하다.**

## 반영된 수정 사항 (실물 카드로 재확인 필요)

### 1. "P9, Y8 모두 따기" — 4인 난이도

- 한국어 1차 자료: `P9, Y8 / 233` → 3인=2, 4인=3, 5인=3
- 영어 2차 자료: `(2/2/3) Win the pink 9 and yellow 8` → 3인=2, 4인=**2**, 5인=3
- **현재 데이터**: 영어 자료를 따라 4인 난이도를 **2**로 반영함
  (`data/deep_sea_crew/tasks.json`의 `win_cards`, `cards: ["P9", "Y8"]` 항목)

### 2. "카드값이 N보다 크다/작다" 트릭 — threshold=7 카드의 조건 방향

- 한국어 1차 자료: "모든 카드값이 아래 수보다 **큰** 트릭 따기 (잠수함 포함 불가)"
  항목 아래에 `5 / 234`와 `7 / 233` 두 장이 나란히 적혀 있었음 (둘 다 "크다"로 기록)
- 영어 2차 자료: 두 장이 서로 다른 조건이었음
  - `(2/3/4) Win a trick where all cards are of greater value than 5` (5보다 **크다**)
  - `(2/3/3) Win a trick where all cards are of lower value than 7 without submarines` (7보다 **작다**)
- **현재 데이터**: threshold=5 카드는 `win_trick_all_above`(초과) 그대로 두고,
  threshold=7 카드는 `win_trick_all_below`(미만)로 kind 자체를 변경함
  — 난이도 숫자(2/3/3)는 애초에 일치했으므로 그대로 유지
- 엔진에 `WIN_TRICK_ALL_BELOW`라는 새 TaskKind를 추가해서 반영 (`tasks.py`)

## 참고: 영어 자료에만 있고 엔진이 아직 구현하지 않은 물리 규칙

영어 자료의 잠수함 관련 미션 몇 개에는 "deal new cards if someone has X in hand"
(특정 카드 조합이 한 사람 손에 몰리면 다시 배분)라는 재배분(redeal) 조건이 붙어 있었다:

- "Win exactly one submarine (deal new cards if someone has all submarines in hand)"
- "Win the 1 submarine and no other (deal new cards if someone has submarines no. 1 and 4 or 1,2,3 in hand)"
- "Win the 2 submarine and no other (deal new cards if someone has submarines no. 2 and 4 or 1,2,3 in hand)"
- "Win exactly two submarines (deal new cards if someone has submarines no. 2,3,4 in hand)"
- "Win exactly three submarines (deal new cards if someone has all submarines in hand)"

이런 "특정 손패 조합이 나오면 그 판을 무효로 하고 다시 배분한다"는 규칙은 현재 엔진에
없다 (해당 미션 자체의 승패 판정 로직은 정상 구현되어 있음 — 다만 극단적으로 불리한/유리한
손패가 나왔을 때 판을 새로 시작하는 안전장치가 없다는 뜻). 실물 규칙서로 확인 후 필요하면
`engine.py`의 `new_game`/딜링 로직에 반영할 것.

## 그 외 94장

나머지 94장은 카드 구성(색상/숫자/잠수함), 조건, 3/4/5인 난이도 숫자까지 한국어·영어
두 자료가 모두 일치했다. (2026-08-19 기준, 대조 스크립트로 96장 전수 확인)
