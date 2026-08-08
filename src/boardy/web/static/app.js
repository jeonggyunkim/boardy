let ws = null;
let mySeat = null;
let selectedForComm = null;
let lastState = null;
let games = [];

const suitClass = (code) => ({ Y: "yellow", P: "pink", G: "green", B: "blue", S: "submarine" }[code[0]] || "");

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

function connect(code, name) {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws/${code}?name=${encodeURIComponent(name)}`);
  ws.onmessage = (ev) => handleMessage(JSON.parse(ev.data));
  ws.onclose = () => console.log("disconnected");
  el("roomCode").textContent = code.toUpperCase();
}

function handleMessage(msg) {
  if (msg.type === "error") {
    alert(msg.message);
    return;
  }
  if (msg.type === "joined") {
    mySeat = msg.seat;
    hide("landing");
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
  selectedForComm = null;
  hide("game");
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

function cardEl(code, { clickable, selected } = {}) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = `card ${suitClass(code)}` + (clickable ? "" : " disabled") + (selected ? " selected" : "");
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

// Animates trick-card-wrap elements sliding into the winner's pile and
// fading out. Relies on #playerBoards already being rendered (for
// pile-N's position) before this is called.
function flyCardsToPile(cardEls, winnerSeat) {
  const pileEl = document.getElementById(`pile-${winnerSeat}`);
  if (!pileEl || !cardEls.length) return;
  const pileRect = pileEl.getBoundingClientRect();
  // A timer (not requestAnimationFrame) so the transition still fires even
  // if the tab is backgrounded/unfocused when a trick resolves -- rAF only
  // runs while the page is actually compositing frames.
  setTimeout(() => {
    cardEls.forEach((wrap) => {
      const rect = wrap.getBoundingClientRect();
      const dx = pileRect.left + pileRect.width / 2 - (rect.left + rect.width / 2);
      const dy = pileRect.top + pileRect.height / 2 - (rect.top + rect.height / 2);
      wrap.style.transform = `translate(${dx}px, ${dy}px) scale(0.35)`;
      wrap.style.opacity = "0";
    });
  }, 20);
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
    name.textContent = `P${i}${i === s.seat ? "(나)" : ""}${meta.name ? " " + meta.name : ""}`;
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

    container.appendChild(board);
  }
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

  const taskDiv = el("taskList");
  taskDiv.innerHTML = "<b>과제</b><br>";
  s.tasks.forEach((t) => {
    const p = document.createElement("div");
    p.className = "task " + (t.resolved ? (t.success ? "ok" : "failed") : "");
    p.textContent = t.describe;
    taskDiv.appendChild(p);
  });

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
  } else if (lastTrick) {
    // trick_in_progress clears the instant the last card is played, so
    // without this the whole table would blink empty before anyone can
    // see what was played -- keep showing the just-finished trick until
    // the next one starts filling up, then slide the cards into the
    // winner's pile so it reads as "the trick moved there" rather than
    // just a number ticking up.
    const heading = document.createElement("b");
    heading.textContent = `트릭 #${lastTrick.number} - P${lastTrick.winner} 승리!`;
    table.appendChild(heading);
    table.appendChild(document.createElement("br"));
    const cardEls = [];
    for (const [seat, code] of Object.entries(lastTrick.cards)) {
      const wrap = trickCardSpan(seat, code, seat == lastTrick.winner);
      table.appendChild(wrap);
      cardEls.push(wrap);
    }
    flyCardsToPile(cardEls, lastTrick.winner);
  } else {
    table.innerHTML = `<b>트릭 #${s.trick_number}</b>`;
  }

  const sigDiv = el("signals");
  const sigEntries = Object.entries(s.signals);
  sigDiv.innerHTML = sigEntries.length
    ? "<b>통신 신호</b>: " +
      sigEntries.map(([p, sig]) => `P${p}=${sig.card}(${sig.marker})`).join("  ")
    : "";

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
    const commOnly = !legal && s.can_communicate;
    const card = cardEl(code, { clickable: legal || commOnly, selected: code === selectedForComm });
    if (commOnly) card.classList.add("comm-only");
    card.title = legal ? "클릭해서 플레이" : commOnly ? "클릭해서 통신 신호로 선택" : "";
    card.onclick = () => {
      if (legal) {
        ws.send(JSON.stringify({ type: "play", action: code }));
        selectedForComm = null;
      } else if (commOnly) {
        selectedForComm = selectedForComm === code ? null : code;
        renderDeepSeaCrew(lastState);
      }
    };
    handDiv.appendChild(card);
  });

  el("commBtn").disabled = !(s.can_communicate && selectedForComm);
  el("commBtn").onclick = () => {
    if (selectedForComm) {
      ws.send(JSON.stringify({ type: "communicate", action: selectedForComm }));
      selectedForComm = null;
    }
  };
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
      const point = document.createElement("button");
      point.type = "button";
      point.className = "gomoku-point" + (legal ? " legal" : "");
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
  connect(data.code, name);
};

el("joinBtn").onclick = () => {
  const code = el("joinCode").value.trim();
  const name = el("joinName").value.trim() || "player";
  if (!code) {
    alert("방 코드를 입력하세요");
    return;
  }
  connect(code, name);
};

el("addAiBtn").onclick = () =>
  ws.send(JSON.stringify({ type: "add_ai", mode: el("aiMode").value }));
el("startBtn").onclick = () => ws.send(JSON.stringify({ type: "start" }));

loadGames();
