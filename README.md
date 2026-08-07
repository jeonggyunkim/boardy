# Boardy — Deep Sea Crew AI

협력 보드게임 "The Crew: Mission Deep Sea"를 함께 플레이하는 AI 플레이어와,
그 AI와 함께 온라인에서 실시간으로 플레이할 수 있는 서비스를 만드는 프로젝트.

개발 계획은 [docs/PLAN.md](docs/PLAN.md) 참고. Phase 1(CLI 룰 엔진), Phase 2(자기대국 학습
파이프라인), Phase 3(실시간 웹 서비스 뼈대)까지 진행됨. 과제 카드 내용은 실제 룰북을
확보하기 전까지 placeholder 데이터(`data/tasks.json`)를 사용한다.

## 설치

```bash
python -m venv .venv
.venv/Scripts/activate  # Windows
pip install -e ".[dev]"
```

## 플레이 (CLI)

```bash
python -m deepsea.cli --players 3 --difficulty 8
```

## 학습 (AI 플레이어)

```bash
python -m deepsea.train --iterations 15 --games-per-iter 15
python -m deepsea.evaluate --checkpoint checkpoints/latest.pt --num-games 30
```

## 온라인 플레이 (웹)

```bash
python -m deepsea.web.server   # http://127.0.0.1:8000
```

방을 만들고(인원수/난이도 지정), 부족한 자리는 "AI 추가"로 채운 뒤 "게임 시작"을 누르면
같은 방 코드로 접속한 다른 브라우저 탭/사용자와 실시간으로 함께 플레이할 수 있다.
아직 AI 좌석은 RandomPlayer만 연결돼 있고, 학습된 체크포인트를 붙이는 건 다음 단계.

## 테스트

```bash
pytest
```
