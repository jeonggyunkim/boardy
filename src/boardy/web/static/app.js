let ws = null;
let mySeat = null;
let lastState = null;
let games = [];
// Trick number whose table display was cleared by clicking "다음", so it
// stays cleared across re-renders until the next trick actually starts
// (see renderDeepSeaCrew / the nextTrickBtn handler).
let acknowledgedTrick = null;

const suitClass = (code) => ({ Y: "yellow", P: "pink", G: "green", B: "blue", S: "submarine" }[code[0]] || "");

// Mirrors communication.py's valid_marker(): which Sonar marker (if any)
// `code` would truthfully get if revealed from `hand`. Own hand is fully
// known client-side, so this can be previewed before the click is sent.
function cardMarker(code, hand) {
  const suit = code[0];
  const sameSuit = hand.filter((c) => c[0] === suit);
  if (sameSuit.length === 1) return "only";
  const rankOf = (c) => parseInt(c.slice(1), 10);
  const ranks = sameSuit.map(rankOf);
  const r = rankOf(code);
  if (r === Math.max(...ranks)) return "highest";
  if (r === Math.min(...ranks)) return "lowest";
  return null;
}

const MARKER_POS = { highest: "top", only: "mid", lowest: "bottom" };
const MARKER_LABEL_KO = { highest: "최고", only: "유일", lowest: "최저" };

// Wraps a card element with a small Sonar token glued to its top/middle/
// bottom edge, positioned per MARKER_POS -- top = highest, middle = only,
// bottom = lowest (see docs/deep_sea_crew_rules.md's 통신 section).
function cardWithToken(cardNode, marker) {
  const wrap = document.createElement("span");
  wrap.className = "card-wrap";
  wrap.appendChild(cardNode);
  const pos = MARKER_POS[marker];
  if (pos) {
    const token = document.createElement("span");
    token.className = `comm-token token-${pos}`;
    token.title = `표시: ${MARKER_LABEL_KO[marker]}`;
    wrap.appendChild(token);
  }
  return wrap;
}

function el(id) { return document.getElementById(id); }
function show(id) { el(id).classList.remove("hidden"); }
function hide(id) { el(id).classList.add("hidden"); }

// ---------- lobby / connection ----------

async function loadGames() {
  const res = await fetch("/api/games");
  const data = await res.json();
  games = data.games || [];
  const select = el("gameSelect");
  select.innerHTML = "";
  games.forEach((g) => {
    const opt = document.createElement("option");
    opt.value = g.slug;
    opt.textContent = g.name;
    select.appendChild(opt);
  });
  updateGameFields();
}

function updateGameFields() {
  const g = games.find((g) => g.slug === el("gameSelect").value);
  if (!g) return;
  el("gameDesc").textContent = g.description;
  el("np").min = g.min_players;
  el("np").max = g.max_players;
  el("np").value = Math.min(Math.max(parseInt(el("np").value, 10) || g.min_players, g.min_players), g.max_players);
  el("diffLabel").classList.toggle("hidden", g.slug !== "deep_sea_crew");
}

function connect(code, name, seat) {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const seatParam = seat === undefined || seat === null ? "" : `&seat=${seat}`;
  ws = new WebSocket(`${proto}://${location.host}/ws/${code}?name=${encodeURIComponent(name)}${seatParam}`);
  ws.onmessage = (ev) => handleMessage(JSON.parse(ev.data));
  ws.onclose = () => console.log("disconnected");
  el("roomCode").textContent = code.toUpperCase();
}

// Shows the empty/taken seats for `code` and lets the user click one to
// join as that specific player number (Gomoku: seat 0 = Black, 1 = White).
async function showSeatPicker(code, name) {
  const res = await fetch(`/api/rooms/${code}`);
  const info = await res.json();
  if (info.error) {
    alert(info.error);
    return;
  }
  hide("landing");
  show("seatPicker");
  el("pickerRoomCode").textContent = code.toUpperCase();
  const container = el("seatButtons");
  container.innerHTML = "";
  info.players.forEach((p, i) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "seat-btn";
    const taken = !!p.name;
    btn.disabled = taken || info.started;
    btn.textContent = taken ? `Player ${i} — ${p.name} (${p.kind}, 이미 참가함)` : `Player ${i} — 비어 있음`;
    btn.onclick = () => connect(code, name, i);
    container.appendChild(btn);
  });
}

function handleMessage(msg) {
  if (msg.type === "error") {
    alert(msg.message);
    return;
  }
  if (msg.type === "joined") {
    mySeat = msg.seat;
    acknowledgedTrick = null;
    hide("landing");
    hide("seatPicker");
    show("lobby");
    return;
  }
  if (msg.type === "lobby") {
    renderLobby(msg);
    return;
  }
  if (msg.type === "state") {
    mySeat = msg.seat;
    lastState = msg;
    hide("landing");
    hide("seatPicker");
    hide("lobby");
    show("game");
    if (msg.game === "gomoku") {
      show("gomokuView");
      hide("dscView");
      renderGomoku(msg);
    } else {
      show("dscView");
      hide("gomokuView");
      renderDeepSeaCrew(msg);
    }
    // player_to_act is null exactly when a game has ended, for every game
    // shape (see boardy.core.game_spec) -- generic "game over" signal.
    if (msg.player_to_act === null) {
      show("postGameControls");
    } else {
      hide("postGameControls");
    }
    return;
  }
}

el("homeBtn").onclick = () => {
  if (ws) {
    ws.onclose = null;
    ws.close();
    ws = null;
  }
  lastState = null;
  mySeat = null;
  animatedTrickNumber = null;
  hide("game");
  hide("seatPicker");
  hide("lobby");
  hide("postGameControls");
  hide("outcomeBanner");
  show("landing");
};

function renderLobby(msg) {
  hide("landing");
  show("lobby");
  el("roomCode").textContent = msg.code;
  const list = el("seatList");
  list.innerHTML = "";
  msg.players.forEach((p, i) => {
    const li = document.createElement("li");
    li.textContent = p.name ? `Seat ${i}: ${p.name} (${p.kind})` : `Seat ${i}: (empty)`;
    list.appendChild(li);
  });
  const full = msg.players.every((p) => p.name);
  el("startBtn").disabled = !full;
}

// ---------- Deep Sea Crew rendering ----------

function cardEl(code, { clickable } = {}) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = `card ${suitClass(code)}` + (clickable ? "" : " disabled");
  btn.textContent = code;
  btn.disabled = !clickable;
  return btn;
}

function trickCardSpan(seat, code, isWinner = false) {
  const wrap = document.createElement("span");
  wrap.className = "trick-card-wrap" + (isWinner ? " winner" : "");
  wrap.style.marginRight = "0.5rem";
  const label = document.createElement("small");
  label.textContent = `P${seat}${isWinner ? "★" : ""}: `;
  wrap.appendChild(label);
  wrap.appendChild(cardEl(code, { clickable: false }));
  return wrap;
}

function renderPlayerBoards(s) {
  const container = el("playerBoards");
  container.innerHTML = "";
  for (let i = 0; i < s.num_players; i++) {
    const board = document.createElement("div");
    board.className = "player-board" + (s.player_to_act === i ? " to-act" : "");

    const name = document.createElement("div");
    name.className = "player-name";
    const meta = s.players[i] || {};
    const leaderMark = i === s.current_leader ? "\u{1F451} " : "";
    name.textContent = `${leaderMark}P${i}${i === s.seat ? "(나)" : ""}${meta.name ? " " + meta.name : ""}`;
    board.appendChild(name);

    const pile = document.createElement("div");
    pile.className = "pile";
    pile.id = `pile-${i}`;
    const count = s.tricks_won[i];
    if (count === 0) {
      const empty = document.createElement("div");
      empty.className = "pile-empty";
      pile.appendChild(empty);
    } else {
      const shown = Math.min(count, 5);
      for (let k = 0; k < shown; k++) {
        const card = document.createElement("div");
        card.className = "pile-card";
        card.style.transform = `translate(${k * 2}px, ${-k * 2}px)`;
        pile.appendChild(card);
      }
    }
    board.appendChild(pile);

    const countLabel = document.createElement("div");
    countLabel.className = "pile-count";
    countLabel.textContent = `트릭 ${count}개`;
    board.appendChild(countLabel);

    // this player's drafted tasks, so it's clear who picked what
    const taskDiv = document.createElement("div");
    taskDiv.className = "player-tasks";
    s.tasks
      .filter((t) => t.owner === i)
      .forEach((t) => {
        const row = document.createElement("div");
        row.className = "mini-task " + (t.resolved ? (t.success ? "ok" : "failed") : "");
        row.textContent = t.describe_plain;
        taskDiv.appendChild(row);
      });
    board.appendChild(taskDiv);

    // this player's revealed Sonar signal (public info -- everyone sees
    // it, same as the physical game: a face-up card with a token on it)
    const sig = s.signals[i];
    if (sig) {
      const sigWrap = cardWithToken(cardEl(sig.card, { clickable: false }), sig.marker);
      sigWrap.classList.add("signal-slot");
      board.appendChild(sigWrap);
    }

    container.appendChild(board);
  }
}

function renderDraft(s) {
  const isMyTurn = s.player_to_act === s.seat;
  const actingPlayer = s.player_to_act !== null ? s.players[s.player_to_act] : null;
  const actingIsAi = actingPlayer && actingPlayer.kind === "ai";
  const turnText = isMyTurn
    ? "과제 뽑기: 당신 차례 — 원하는 과제를 선택하세요"
    : actingIsAi
    ? `${actingPlayer.name} 과제 선택 중...`
    : `P${s.player_to_act} 과제 선택 대기`;
  el("draftStatus").textContent = `\u{1F451} 사령관: P${s.current_leader}  |  ${turnText}`;

  const pool = el("draftPool");
  pool.innerHTML = "";
  s.available_tasks.forEach((t) => {
    const btn = document.createElement("button");
    const pickable = isMyTurn && s.legal_moves.includes(t.id);
    btn.className = "draft-task" + (pickable ? " pickable" : "");
    btn.disabled = !pickable;
    btn.innerHTML = `<span class="diff">난이도 ${t.difficulty}</span>${t.describe}`;
    btn.onclick = () => {
      if (pickable) ws.send(JSON.stringify({ type: "play", action: t.id }));
    };
    pool.appendChild(btn);
  });
}

function renderDeepSeaCrew(s) {
  if (s.outcome !== null) {
    const banner = el("outcomeBanner");
    banner.classList.remove("hidden", "success", "failure");
    banner.classList.add(s.outcome ? "success" : "failure");
    banner.textContent = s.outcome ? "미션 성공!" : "미션 실패.";
  } else {
    hide("outcomeBanner");
  }

  renderPlayerBoards(s);

  if (s.phase === "task_draft") {
    show("draftView");
    hide("playView");
    renderDraft(s);
    return;
  }
  show("playView");
  hide("draftView");

  const table = el("table");
  table.innerHTML = "";
  const inProgress = Object.keys(s.trick_in_progress).length > 0;
  const lastTrick = s.history.length ? s.history[s.history.length - 1] : null;
  if (inProgress) {
    const heading = document.createElement("b");
    heading.textContent = `트릭 #${s.trick_number}`;
    table.appendChild(heading);
    table.appendChild(document.createElement("br"));
    for (const [seat, code] of Object.entries(s.trick_in_progress)) {
      table.appendChild(trickCardSpan(seat, code));
    }
  } else if (lastTrick && lastTrick.number !== acknowledgedTrick) {
    // trick_in_progress clears the instant the last card is played, so
    // without this the whole table would blink empty before anyone can
    // see what was played -- keep showing the just-finished trick until
    // "다음" is clicked (see the nextTrickBtn handler, which clears it).
    const heading = document.createElement("b");
    heading.textContent = `트릭 #${lastTrick.number} - P${lastTrick.winner} 승리!`;
    table.appendChild(heading);
    table.appendChild(document.createElement("br"));
    for (const [seat, code] of Object.entries(lastTrick.cards)) {
      table.appendChild(trickCardSpan(seat, code, seat == lastTrick.winner));
    }
  } else {
    table.innerHTML = `<b>트릭 #${s.trick_number}</b>`;
  }

  el("nextTrickBtn").classList.toggle("hidden", !s.awaiting_next);
  el("nextTrickBtn").onclick = () => {
    // Clear the just-finished trick immediately instead of leaving it
    // displayed until the next broadcast arrives -- "다음" should mean
    // "done reviewing this", not linger until something else happens to
    // redraw the table.
    if (lastTrick) acknowledgedTrick = lastTrick.number;
    table.innerHTML = `<b>트릭 #${s.trick_number}</b>`;
    ws.send(JSON.stringify({ type: "next" }));
  };

  // gated by awaiting_next too: the trick that just finished must be
  // acknowledged via "다음" before anyone (including the next leader) can act
  const isMyTurn = s.player_to_act === s.seat && !s.awaiting_next;
  const actingPlayer = s.player_to_act !== null ? s.players[s.player_to_act] : null;
  const actingIsAi = actingPlayer && actingPlayer.kind === "ai";
  el("turnIndicator").textContent = s.awaiting_next
    ? "트릭 결과를 확인하고 [다음]을 누르세요"
    : s.player_to_act === null
    ? "게임 종료"
    : isMyTurn
    ? "당신 차례"
    : actingIsAi
    ? `${actingPlayer.name} 생각 중...`
    : `P${s.player_to_act} 차례 대기`;

  const handDiv = el("hand");
  handDiv.innerHTML = "";
  s.hand.forEach((code) => {
    const legal = isMyTurn && s.legal_moves.includes(code);
    const marker = s.can_communicate ? cardMarker(code, s.hand) : null;
    // A card can only signal if it's truthfully the highest/lowest/only
    // of its suit in hand (see cardMarker) -- a middling card has no
    // valid marker and can't be used to communicate, same as the server.
    const commOnly = !legal && s.can_communicate && marker !== null;
    const card = cardEl(code, { clickable: legal || commOnly });
    card.title = legal ? "클릭해서 플레이" : commOnly ? `클릭해서 통신 토큰 놓기 (${MARKER_LABEL_KO[marker]})` : "";
    card.onclick = () => {
      if (legal) {
        ws.send(JSON.stringify({ type: "play", action: code }));
      } else if (commOnly) {
        ws.send(JSON.stringify({ type: "communicate", action: code }));
      }
    };
    handDiv.appendChild(commOnly ? cardWithToken(card, marker) : card);
  });
}

// ---------- Gomoku rendering ----------

function renderGomoku(s) {
  if (s.winner !== null) {
    const banner = el("outcomeBanner");
    banner.classList.remove("hidden", "success", "failure");
    const iWon = s.winner_seat === s.seat;
    const isDraw = s.winner === "draw";
    banner.classList.add(isDraw ? "failure" : iWon ? "success" : "failure");
    banner.textContent = isDraw ? "무승부." : iWon ? "당신 승리!" : `${s.winner === "black" ? "흑" : "백"} 승리.`;
  } else {
    hide("outcomeBanner");
  }

  const isMyTurn = s.player_to_act === s.seat;
  const actingPlayer = s.player_to_act !== null ? s.players[s.player_to_act] : null;
  const actingIsAi = actingPlayer && actingPlayer.kind === "ai";
  el("gomokuStatus").textContent =
    s.player_to_act === null
      ? "게임 종료"
      : isMyTurn
      ? `당신 차례 (${s.my_color === "black" ? "흑" : "백"})`
      : actingIsAi
      ? `${actingPlayer.name} 생각 중...`
      : `P${s.player_to_act} 차례 대기`;

  renderGomokuBoard(s, isMyTurn);
}

const GOMOKU_CELL = 32; // px between line intersections
const GOMOKU_MARGIN = 20; // px padding so edge stones aren't clipped

function renderGomokuBoard(s, isMyTurn) {
  const legalSet = new Set(s.legal_moves);
  const boardDiv = el("gomokuBoard");
  boardDiv.innerHTML = "";
  const span = (s.size - 1) * GOMOKU_CELL;
  boardDiv.style.width = `${span + GOMOKU_MARGIN * 2}px`;
  boardDiv.style.height = `${span + GOMOKU_MARGIN * 2}px`;

  // grid lines, drawn between the first and last intersection on each axis
  for (let i = 0; i < s.size; i++) {
    const h = document.createElement("div");
    h.className = "gomoku-line";
    h.style.left = `${GOMOKU_MARGIN}px`;
    h.style.top = `${GOMOKU_MARGIN + i * GOMOKU_CELL}px`;
    h.style.width = `${span}px`;
    h.style.height = "1px";
    boardDiv.appendChild(h);

    const v = document.createElement("div");
    v.className = "gomoku-line";
    v.style.left = `${GOMOKU_MARGIN + i * GOMOKU_CELL}px`;
    v.style.top = `${GOMOKU_MARGIN}px`;
    v.style.width = "1px";
    v.style.height = `${span}px`;
    boardDiv.appendChild(v);
  }

  // one clickable point per intersection, stone rendered on top when occupied
  for (let r = 0; r < s.size; r++) {
    for (let c = 0; c < s.size; c++) {
      const value = s.board[r * s.size + c];
      const key = `${r},${c}`;
      const legal = isMyTurn && legalSet.has(key);
      // legal implies it's my turn, so s.my_color is the acting player's
      // color here -- highlight legal points in that color, not always white.
      const point = document.createElement("button");
      point.type = "button";
      point.className = "gomoku-point" + (legal ? ` legal turn-${s.my_color}` : "");
      point.style.left = `${GOMOKU_MARGIN + c * GOMOKU_CELL}px`;
      point.style.top = `${GOMOKU_MARGIN + r * GOMOKU_CELL}px`;
      point.disabled = !legal;
      if (s.last_move && s.last_move[0] === r && s.last_move[1] === c) point.classList.add("last-move");
      if (value !== 0) {
        const stone = document.createElement("span");
        stone.className = "stone " + (value === 1 ? "black" : "white");
        point.appendChild(stone);
      }
      point.onclick = () => {
        if (legal) ws.send(JSON.stringify({ type: "play", action: key }));
      };
      boardDiv.appendChild(point);
    }
  }
}

// ---------- landing page actions ----------

el("gameSelect").onchange = updateGameFields;

el("createBtn").onclick = async () => {
  const game = el("gameSelect").value;
  const num_players = parseInt(el("np").value, 10);
  const difficulty = parseInt(el("diff").value, 10);
  const res = await fetch("/api/rooms", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ game, num_players, difficulty }),
  });
  const data = await res.json();
  if (data.error) {
    alert(data.error);
    return;
  }
  const name = el("createName").value.trim() || "player";
  showSeatPicker(data.code, name);
};

el("joinBtn").onclick = () => {
  const code = el("joinCode").value.trim();
  const name = el("joinName").value.trim() || "player";
  if (!code) {
    alert("방 코드를 입력하세요");
    return;
  }
  showSeatPicker(code, name);
};

el("addAiBtn").onclick = () =>
  ws.send(JSON.stringify({ type: "add_ai", mode: el("aiMode").value }));
el("startBtn").onclick = () => ws.send(JSON.stringify({ type: "start" }));

loadGames();
