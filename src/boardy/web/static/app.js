let ws = null;
let mySeat = null;
let lastState = null;
let games = [];
// Trick number for which the "확인" step (reviewing the just-finished
// trick) has been done -- either clicked, or skipped because there was
// nothing to review (trick 1). Communication/준비 UI only shows once this
// matches the current trick_ready window's trick number (see renderReady).
let trickReadyAckedFor = null;
// {game, num_players, difficulty, name, seat, aiModes} for the room THIS
// client created, so "다시 플레이" can spin up an equivalent one -- null
// if this client joined someone else's room instead (nothing to replay).
let lastSetup = null;
// Set by playAgain() right before connecting to the freshly created room;
// consumed by the "joined" handler to auto-add the same AI seats and
// start, without the user re-clicking through the lobby.
let pendingAutoSetup = null;

const suitClass = (code) => ({ Y: "yellow", P: "pink", G: "green", B: "blue", S: "submarine" }[code[0]] || "");

// Mirrors communication.py's valid_marker(): which Sonar marker (if any)
// `code` would truthfully get if revealed from `hand`. Own hand is fully
// known client-side, so this can be previewed before the click is sent.
function cardMarker(code, hand) {
  const suit = code[0];
  if (suit === "S") return null; // submarines can't be signaled
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
  el("rulesLink").href = `/rules/${g.slug}`;
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
    btn.onclick = () => {
      if (lastSetup) lastSetup.seat = i;
      connect(code, name, i);
    };
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
    trickReadyAckedFor = null;
    hide("landing");
    hide("seatPicker");
    show("lobby");
    if (pendingAutoSetup) {
      const modes = pendingAutoSetup.aiModes;
      pendingAutoSetup = null;
      modes.forEach((mode) => {
        if (lastSetup) lastSetup.aiModes.push(mode);
        ws.send(JSON.stringify({ type: "add_ai", mode }));
      });
      ws.send(JSON.stringify({ type: "start" }));
    }
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
    el("inGameRulesLink").href = `/rules/${msg.game}`;
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
  trickReadyAckedFor = null;
  pendingAutoSetup = null;
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

// s.trick_in_progress / a TrickRecord's .cards is a {seat: card} object,
// and JSON object keys that look like integers are always iterated in
// numeric order by JS (Object.entries ignores insertion order for them)
// -- so rendering straight from it shows seat order, not play order.
// Play order is always leader, leader+1, ... wrapping around the table.
function playOrderFor(leader, numPlayers) {
  return Array.from({ length: numPlayers }, (_, i) => (leader + i) % numPlayers);
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
    // 👑 = commander (fixed for the whole game, sets draft order); ▶ =
    // this trick's leader (changes every trick, winner leads next) --
    // these are two different things and can be different players.
    const commanderMark = i === s.commander ? "\u{1F451}" : "";
    const leaderMark = i === s.current_leader ? "\u{25B6}" : "";
    const marks = [commanderMark, leaderMark].filter(Boolean).join(" ");
    name.textContent = `${marks ? marks + " " : ""}P${i}${i === s.seat ? "(나)" : ""}${meta.name ? " " + meta.name : ""}`;
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

    // who's already readied up for the next trick (see renderReady)
    if (s.phase === "trick_ready" && s.ready_seats.includes(i)) {
      const readyMark = document.createElement("div");
      readyMark.className = "ready-mark";
      readyMark.textContent = "✅ 준비 완료";
      board.appendChild(readyMark);
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
  el("draftStatus").textContent = `\u{1F451} 사령관: P${s.commander}  |  ${turnText}`;

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

  // Hands are dealt before drafting starts (see engine.new_game), so a
  // player picking a task should already be able to see what they have to
  // work with -- otherwise they're drafting blind.
  const handDiv = el("draftHand");
  handDiv.innerHTML = "";
  s.hand.forEach((code) => handDiv.appendChild(cardEl(code, { clickable: false })));
}

// The "trick_ready" phase: everyone must individually confirm before the
// next trick starts (see engine.py's GameState.mark_ready). Two steps:
// 1. If there's a just-finished trick to review, show it + "확인" --
//    clicking clears it (purely a local display gate; the server already
//    considers the window open regardless, see trickReadyAckedFor).
// 2. Once acknowledged (or there was nothing to review, e.g. trick 1):
//    show communicate-eligible hand cards + "준비", and who's already
//    readied. Communicating is only possible in this exact window --
//    after "확인", before clicking "준비" -- matching what the server
//    actually enforces (GameState.communicate).
function renderReady(s) {
  const lastTrick = s.history.length ? s.history[s.history.length - 1] : null;
  const needsAck = lastTrick && trickReadyAckedFor !== s.trick_number;

  const reviewTable = el("trickReviewTable");
  const confirmBtn = el("confirmBtn");
  const readyBlock = el("readyBlock");

  if (needsAck) {
    el("readyStatus").textContent = "트릭 결과를 확인하세요";
    reviewTable.innerHTML = "";
    const heading = document.createElement("b");
    heading.textContent = `트릭 #${lastTrick.number} - P${lastTrick.winner} 승리!`;
    reviewTable.appendChild(heading);
    reviewTable.appendChild(document.createElement("br"));
    for (const seat of playOrderFor(lastTrick.leader, s.num_players)) {
      if (seat in lastTrick.cards) reviewTable.appendChild(trickCardSpan(seat, lastTrick.cards[seat], seat == lastTrick.winner));
    }
    show("confirmBtn");
    hide("readyBlock");
    confirmBtn.onclick = () => {
      // Keyed by s.trick_number (the *upcoming* trick's number, already
      // incremented past lastTrick.number by the time we're in this
      // window) so the needsAck check above actually matches next render.
      trickReadyAckedFor = s.trick_number;
      renderReady(lastState);
    };
    return;
  }

  reviewTable.innerHTML = "";
  hide("confirmBtn");
  show("readyBlock");

  const amReady = s.ready_seats.includes(s.seat);
  const notReady = [];
  for (let i = 0; i < s.num_players; i++) {
    if (!s.ready_seats.includes(i)) notReady.push(`P${i}`);
  }
  el("readyStatus").textContent = notReady.length ? `대기 중: ${notReady.join(", ")}` : "모두 준비 완료";

  const handDiv = el("readyHand");
  handDiv.innerHTML = "";
  s.hand.forEach((code) => {
    const marker = s.can_communicate && !amReady ? cardMarker(code, s.hand) : null;
    const commOnly = marker !== null;
    const card = cardEl(code, { clickable: commOnly });
    card.title = commOnly ? `클릭해서 통신 토큰 놓기 (${MARKER_LABEL_KO[marker]})` : "";
    card.onclick = () => {
      if (commOnly) ws.send(JSON.stringify({ type: "communicate", action: code }));
    };
    handDiv.appendChild(commOnly ? cardWithToken(card, marker) : card);
  });

  const readyBtn = el("readyBtn");
  readyBtn.disabled = amReady;
  readyBtn.textContent = amReady ? "준비 완료 (대기 중...)" : "준비";
  readyBtn.onclick = () => ws.send(JSON.stringify({ type: "ready" }));
}

function renderPlaying(s) {
  const table = el("table");
  table.innerHTML = "";
  const inProgress = Object.keys(s.trick_in_progress).length > 0;
  if (inProgress) {
    const heading = document.createElement("b");
    heading.textContent = `트릭 #${s.trick_number}`;
    table.appendChild(heading);
    table.appendChild(document.createElement("br"));
    for (const seat of playOrderFor(s.current_leader, s.num_players)) {
      if (seat in s.trick_in_progress) table.appendChild(trickCardSpan(seat, s.trick_in_progress[seat]));
    }
  } else {
    table.innerHTML = `<b>트릭 #${s.trick_number}</b>`;
  }

  const isMyTurn = s.player_to_act === s.seat;
  const actingPlayer = s.player_to_act !== null ? s.players[s.player_to_act] : null;
  const actingIsAi = actingPlayer && actingPlayer.kind === "ai";
  el("turnIndicator").textContent =
    s.player_to_act === null
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
    const card = cardEl(code, { clickable: legal });
    card.title = legal ? "클릭해서 플레이" : "";
    card.onclick = () => {
      if (legal) ws.send(JSON.stringify({ type: "play", action: code }));
    };
    handDiv.appendChild(card);
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

  hide("draftView");
  hide("readyView");
  hide("playView");
  if (s.phase === "task_draft") {
    show("draftView");
    renderDraft(s);
  } else if (s.phase === "trick_ready") {
    show("readyView");
    renderReady(s);
  } else {
    show("playView");
    renderPlaying(s);
  }
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
  // Only a room THIS client created (not one it joined) has a known-full
  // setup to replay -- seat gets filled in once picked, aiModes as they're
  // added (see the seatButtons/addAiBtn handlers).
  lastSetup = { game, num_players, difficulty, name, seat: null, aiModes: [] };
  showSeatPicker(data.code, name);
};

el("joinBtn").onclick = () => {
  const code = el("joinCode").value.trim();
  const name = el("joinName").value.trim() || "player";
  if (!code) {
    alert("방 코드를 입력하세요");
    return;
  }
  lastSetup = null;
  showSeatPicker(code, name);
};

el("addAiBtn").onclick = () => {
  const mode = el("aiMode").value;
  if (lastSetup) lastSetup.aiModes.push(mode);
  ws.send(JSON.stringify({ type: "add_ai", mode }));
};
el("startBtn").onclick = () => ws.send(JSON.stringify({ type: "start" }));

// Recreates a room with the same game/인원수/난이도/좌석/AI 구성 as the one
// that just ended, and auto-starts it -- only available when this client
// was the one who created that room (see lastSetup).
el("playAgainBtn").onclick = async () => {
  if (!lastSetup) {
    el("homeBtn").click();
    return;
  }
  const { game, num_players, difficulty, name, seat, aiModes } = lastSetup;
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
  if (ws) {
    ws.onclose = null;
    ws.close();
    ws = null;
  }
  hide("game");
  hide("postGameControls");
  hide("outcomeBanner");
  trickReadyAckedFor = null;
  lastState = null;
  lastSetup = { game, num_players, difficulty, name, seat, aiModes: [] };
  pendingAutoSetup = { aiModes };
  connect(data.code, name, seat);
};

loadGames();
