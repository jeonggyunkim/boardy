# Boardy — Deep Sea Crew AI

협력 보드게임 "The Crew: Mission Deep Sea"를 함께 플레이하는 AI 플레이어와,
그 AI와 함께 온라인에서 실시간으로 플레이할 수 있는 서비스를 만드는 프로젝트.

개발 계획은 [docs/PLAN.md](docs/PLAN.md) 참고. 현재 Phase 1(CLI 룰 엔진) 진행 중이며,
과제 카드 내용은 실제 룰북을 확보하기 전까지 placeholder 데이터(`data/tasks.json`)를 사용한다.

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

## 테스트

```bash
pytest
```
