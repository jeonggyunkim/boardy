"""Standalone position-analysis tool -- NOT part of the main web app.

Lets you manually place both Black and White stones (turn by turn, same
Renju rules as everywhere else) on a normal board, then hit "Calculate" to
see, for the current position:
  - the value network's output from Black's perspective and from White's
    perspective (same stones, `to_move` flipped -- two separate forward
    passes, since the network's input encoding is to-move-relative)
  - the policy network's raw prior (a single forward pass, no search --
    "glance and guess") for whoever is actually next to move
  - the visit-count distribution after a real 100-simulation MCTS search
    for that same side

Deliberately a separate process/port from `web.server` -- reuses `Board`,
`PolicyValueNet`, `run_mcts`, and `ai.get_shared_net()` as-is (none of
that, or the main web app/GUI, is touched), it just exposes a much more
low-level, single-user debugging view over the same game/model code.

Run: python -m boardy.games.gomoku.analysis_server
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from .ai import get_shared_net, net_source
from .board import BLACK, WHITE, Board
from .engine import new_game
from .mcts import run_mcts

app = FastAPI(title="Gomoku Position Analysis")
_board: Board = new_game()


class PlayRequest(BaseModel):
    r: int
    c: int


def _state_payload() -> dict:
    size = _board.size
    forbidden: dict[str, str] = {}
    if _board.winner is None and _board.renju and _board.to_move == BLACK:
        for i, v in enumerate(_board.cells):
            if v != 0:
                continue
            r, c = divmod(i, size)
            reason = _board.is_forbidden_for_black(r, c)
            if reason is not None:
                forbidden[f"{r},{c}"] = reason
    return {
        "size": size,
        "cells": _board.cells.tolist(),
        "to_move": _board.to_move,
        "last_move": list(_board.last_move) if _board.last_move is not None else None,
        "winner": _board.winner,
        "forbidden_reasons": forbidden,
        "net_source": net_source(),
    }


def _value_from_perspective(board: Board, color: int) -> float:
    """Value net's output for this exact stone layout, as if `color` were
    to move -- requires its own forward pass (not just negating the other
    color's value) since the network's input planes are to-move-relative,
    and (for Black) even the legal-move mask depends on whose turn it is
    (Renju restrictions only apply to Black)."""
    probe = board.clone()
    probe.to_move = color
    _, value = get_shared_net().predict(probe)
    return value


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return _PAGE


@app.get("/state")
def state() -> dict:
    return _state_payload()


@app.post("/play")
def play(req: PlayRequest) -> dict:
    try:
        _board.play(req.r, req.c)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _state_payload()


@app.post("/reset")
def reset() -> dict:
    global _board
    _board = new_game()
    return _state_payload()


@app.post("/analyze")
def analyze() -> dict:
    if _board.winner is not None:
        raise HTTPException(status_code=400, detail="Game already finished -- reset to keep analyzing.")
    net = get_shared_net()
    size = _board.size
    mover = _board.to_move
    legal = _board.legal_moves()

    value_black = _value_from_perspective(_board, BLACK)
    value_white = _value_from_perspective(_board, WHITE)

    prior_arr, _ = net.predict(_board, legal_moves=legal)
    prior = {f"{r},{c}": float(prior_arr[r * size + c]) for r, c in legal}

    visit_probs = run_mcts(_board, net, num_simulations=100, add_noise=False)

    return {
        "current_mover": mover,
        "value_black": value_black,
        "value_white": value_white,
        "policy_prior": prior,
        "visit_probs": visit_probs,
    }


_PAGE = r"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Gomoku Position Analysis</title>
<style>
  body { font-family: system-ui, sans-serif; background: #1e1e1e; color: #eee; padding: 20px; }
  h1 { font-size: 18px; font-weight: 600; }
  .layout { display: flex; gap: 28px; flex-wrap: wrap; align-items: flex-start; }
  .board-block { display: flex; flex-direction: column; align-items: center; gap: 8px; }
  .board-label { font-size: 13px; color: #aaa; }
  .board { display: grid; border: 1px solid #555; }
  .cell { width: 30px; height: 30px; box-sizing: border-box; border: 1px solid #3a3a3a;
          display: flex; align-items: center; justify-content: center; position: relative;
          cursor: pointer; font-size: 10px; color: #ccc; }
  .cell.readonly { cursor: default; }
  .stone { width: 18px; height: 18px; border-radius: 50%; }
  .stone.black { background: #111; border: 1px solid #555; }
  .stone.white { background: #eee; border: 1px solid #999; }
  .last-move { outline: 2px solid #4da6ff; outline-offset: -2px; }
  .forbidden { background: rgba(220, 50, 50, 0.35); }
  .heat-label { position: absolute; bottom: 1px; right: 1px; font-size: 7px; font-family: monospace;
                pointer-events: none; }
  button { background: #2d6cdf; color: white; border: none; padding: 8px 14px; border-radius: 4px;
           cursor: pointer; font-size: 14px; margin-right: 8px; }
  button:hover { background: #1f57b8; }
  button.secondary { background: #444; }
  button.secondary:hover { background: #333; }
  .panel { background: #2a2a2a; border-radius: 6px; padding: 12px 16px; min-width: 220px; }
  .values { display: flex; gap: 20px; margin-bottom: 10px; }
  .value-box { text-align: center; }
  .value-box .num { font-size: 22px; font-weight: 700; }
  .value-box .lbl { font-size: 12px; color: #aaa; }
  .toplist { font-size: 12px; }
  .toplist table { border-collapse: collapse; width: 100%; }
  .toplist td { padding: 2px 6px; border-bottom: 1px solid #3a3a3a; }
  .status { font-size: 13px; color: #aaa; margin: 8px 0; min-height: 18px; }
  .legend { font-size: 11px; color: #888; margin-top: 6px; }
</style>
</head>
<body>
<h1>Gomoku Position Analysis (직접 흑/백 착수 → Calculate)</h1>
<div class="status" id="status"></div>
<div class="layout">
  <div class="board-block">
    <div class="board-label">착수판 (클릭해서 흑/백 번갈아 착수)</div>
    <div class="board" id="board"></div>
    <div>
      <button onclick="doReset()" class="secondary">Reset</button>
      <button onclick="doAnalyze()">Calculate</button>
    </div>
  </div>
  <div class="panel" id="values-panel">
    <div class="values">
      <div class="value-box"><div class="num" id="value-black">-</div><div class="lbl">가치망: 흑 관점 value</div></div>
      <div class="value-box"><div class="num" id="value-white">-</div><div class="lbl">가치망: 백 관점 value</div></div>
    </div>
    <div class="legend" id="mover-note"></div>
  </div>
  <div class="board-block">
    <div class="board-label">정책망 prior (탐색 없이 한 번 본 것, <span id="mover-label-1"></span> 기준)</div>
    <div class="board" id="board-prior"></div>
  </div>
  <div class="board-block">
    <div class="board-label">MCTS 100회 후 visit_probs (<span id="mover-label-2"></span> 기준)</div>
    <div class="board" id="board-visit"></div>
  </div>
</div>

<script>
const SIZE = 15;
let state = null;

function cellKey(r, c) { return r + "," + c; }

function buildGrid(id, clickable) {
  const el = document.getElementById(id);
  el.style.gridTemplateColumns = `repeat(${SIZE}, 30px)`;
  el.innerHTML = "";
  for (let r = 0; r < SIZE; r++) {
    for (let c = 0; c < SIZE; c++) {
      const div = document.createElement("div");
      div.className = "cell" + (clickable ? "" : " readonly");
      div.dataset.r = r;
      div.dataset.c = c;
      if (clickable) div.onclick = () => placeStone(r, c);
      el.appendChild(div);
    }
  }
}

function renderBoard() {
  const el = document.getElementById("board");
  for (const div of el.children) {
    const r = +div.dataset.r, c = +div.dataset.c;
    const idx = r * SIZE + c;
    div.className = "cell";
    div.innerHTML = "";
    const v = state.cells[idx];
    if (v !== 0) {
      const s = document.createElement("div");
      s.className = "stone " + (v === 1 ? "black" : "white");
      div.appendChild(s);
    }
    if (state.last_move && state.last_move[0] === r && state.last_move[1] === c) {
      div.classList.add("last-move");
    }
    if (state.forbidden_reasons[cellKey(r, c)]) {
      div.classList.add("forbidden");
      div.title = state.forbidden_reasons[cellKey(r, c)];
    }
  }
  const moverText = state.to_move === 1 ? "흑" : "백";
  let statusText = `${moverText} 차례 (model: ${state.net_source})`;
  if (state.winner !== null) {
    statusText = state.winner === 0 ? "무승부" : (state.winner === 1 ? "흑 승" : "백 승");
  }
  document.getElementById("status").textContent = statusText;
}

function renderHeat(id, dist) {
  const el = document.getElementById(id);
  const maxV = Math.max(0.0001, ...Object.values(dist || {}));
  for (const div of el.children) {
    const r = +div.dataset.r, c = +div.dataset.c;
    const idx = r * SIZE + c;
    div.innerHTML = "";
    div.style.background = "";
    const v = state.cells[idx];
    if (v !== 0) {
      const s = document.createElement("div");
      s.className = "stone " + (v === 1 ? "black" : "white");
      div.appendChild(s);
      continue;
    }
    const p = dist ? dist[cellKey(r, c)] : undefined;
    if (p !== undefined) {
      const t = p / maxV;
      div.style.background = `rgba(255, 90, 90, ${t.toFixed(3)})`;
      const lbl = document.createElement("div");
      lbl.className = "heat-label";
      lbl.textContent = p.toFixed(3).replace(/^0\./, ".");
      div.appendChild(lbl);
    }
  }
}

async function refresh(newState) {
  state = newState;
  renderBoard();
}

async function placeStone(r, c) {
  const resp = await fetch("/play", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({r, c}),
  });
  if (!resp.ok) {
    const err = await resp.json();
    alert(err.detail);
    return;
  }
  await refresh(await resp.json());
}

async function doReset() {
  const resp = await fetch("/reset", {method: "POST"});
  await refresh(await resp.json());
  buildGrid("board-prior", false);
  buildGrid("board-visit", false);
  document.getElementById("value-black").textContent = "-";
  document.getElementById("value-white").textContent = "-";
  document.getElementById("mover-note").textContent = "";
  document.getElementById("mover-label-1").textContent = "";
  document.getElementById("mover-label-2").textContent = "";
}

async function doAnalyze() {
  document.getElementById("status").textContent = "계산 중... (MCTS 100회, 몇 초 걸릴 수 있음)";
  const resp = await fetch("/analyze", {method: "POST"});
  if (!resp.ok) {
    const err = await resp.json();
    alert(err.detail);
    renderBoard();
    return;
  }
  const result = await resp.json();
  document.getElementById("value-black").textContent = result.value_black.toFixed(3);
  document.getElementById("value-white").textContent = result.value_white.toFixed(3);
  const moverText = result.current_mover === 1 ? "흑" : "백";
  document.getElementById("mover-note").textContent = `(현재 실제 차례: ${moverText} -- prior/visit_probs는 이 쪽 기준)`;
  document.getElementById("mover-label-1").textContent = moverText;
  document.getElementById("mover-label-2").textContent = moverText;
  renderHeat("board-prior", result.policy_prior);
  renderHeat("board-visit", result.visit_probs);
  renderBoard();
}

async function init() {
  buildGrid("board", true);
  buildGrid("board-prior", false);
  buildGrid("board-visit", false);
  const resp = await fetch("/state");
  await refresh(await resp.json());
}
init();
</script>
</body>
</html>
"""


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)


if __name__ == "__main__":
    main()
