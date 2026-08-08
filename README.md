# Boardy — 보드게임 AI 컴패니언

여러 보드게임을 AI 플레이어와 함께 온라인에서 실시간으로 플레이할 수 있는 서비스.
사람 수가 부족해 밸런스가 무너지는 문제를, 그 게임을 배운 AI가 빈 자리를 채워서
해결하려는 프로젝트다. 첫 번째로 지원하는 게임은 **Deep Sea Crew**
("The Crew: Mission Deep Sea" 기반 협력 트릭테이킹).

개발 계획은 [docs/PLAN.md](docs/PLAN.md) 참고. 과제 카드 내용은 실제 룰북을 확보하기
전까지 placeholder 데이터(`data/deep_sea_crew/tasks.json`)를 사용한다.

## 구조

```
src/boardy/
  core/            게임에 무관한 공통 계약 (GameSpec, registry)
  web/             공용 실시간 웹 서비스 (FastAPI + WebSocket) — GameSpec을 통해서만 게임과 통신
  cli.py           `--game <slug>`로 게임별 CLI에 위임하는 최상위 디스패처
  games/
    deep_sea_crew/ 이 게임의 규칙 엔진·AI 학습·CLI 전부 (다른 게임과 내부 구현 공유 없음)
      spec.py      GameSpec으로 감싸서 registry에 등록
data/deep_sea_crew/tasks.json   이 게임의 과제 데이터
tests/deep_sea_crew/            이 게임의 테스트
```

새 게임을 추가하려면 `src/boardy/games/<slug>/`에 규칙 엔진을 구현하고, `spec.py`에서
`GameSpec`으로 감싸 `register()`하고, `games/__init__.py`에서 임포트하면 된다. 트릭테이킹
전용 로직(카드/트릭/통신 등)은 게임마다 근본적으로 다르므로 공유하지 않고, 웹/CLI
호스트 레이어가 필요로 하는 좁은 경계(`GameSpec`)만 표준화했다 — 자세한 계약은
[game_spec.py](src/boardy/core/game_spec.py) 참고.

## 설치

```bash
python -m venv .venv
.venv/Scripts/activate  # Windows
pip install -e ".[dev]"
```

## 플레이 (CLI)

```bash
python -m boardy.cli --game deep_sea_crew --players 3 --difficulty 8
```

## 학습 (AI 플레이어)

```bash
python -m boardy.games.deep_sea_crew.train --iterations 15 --games-per-iter 15
python -m boardy.games.deep_sea_crew.evaluate --checkpoint checkpoints/latest.pt --num-games 30
```

## 온라인 플레이 (웹)

```bash
python -m boardy.web.server   # http://127.0.0.1:8000
```

방을 만들고(인원수/난이도 지정), 부족한 자리는 "AI 추가"로 채운 뒤(랜덤 또는 탐색 기반
"스마트" 중 선택) "게임 시작"을 누르면 같은 방 코드로 접속한 다른 브라우저 탭/사용자와
실시간으로 함께 플레이할 수 있다. 프론트엔드는 지금은 Deep Sea Crew 전용이지만, 백엔드는
`GET /api/games`로 등록된 아무 게임이나 방을 만들 수 있다.

## 테스트

```bash
pytest
```
