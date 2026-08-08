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
    return;
  }
}

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

function renderDeepSeaCrew(s) {
  if (s.outcome !== null) {
    const banner = el("outcomeBanner");
    banner.classList.remove("hidden", "success", "failure");
    banner.classList.add(s.outcome ? "success" : "failure");
    banner.textContent = s.outcome ? "미션 성공!" : "미션 실패.";
  } else {
    hide("outcomeBanner");
  }

  const taskDiv = el("taskList");
  taskDiv.innerHTML = "<b>과제</b><br>";
  s.tasks.forEach((t) => {
    const p = document.createElement("div");
    p.className = "task " + (t.resolved ? (t.success ? "ok" : "failed") : "");
    p.textContent = t.describe;
    taskDiv.appendChild(p);
  });

  const table = el("table");
  table.innerHTML = `<b>트릭 #${s.trick_number}</b><br>`;
  for (const [seat, code] of Object.entries(s.trick_in_progress)) {
    const wrap = document.createElement("span");
    wrap.style.marginRight = "0.5rem";
    const label = document.createElement("small");
    label.textContent = `P${seat}: `;
    wrap.appendChild(label);
    wrap.appendChild(cardEl(code, { clickable: false }));
    table.appendChild(wrap);
  }

  el("handSizes").innerHTML =
    "<b>남은 카드 수</b>: " +
    s.hand_sizes.map((n, i) => `P${i}${i === s.seat ? "(나)" : ""}:${n}`).join("  ");

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

  const legalSet = new Set(s.legal_moves);
  const boardDiv = el("gomokuBoard");
  boardDiv.innerHTML = "";
  for (let r = 0; r < s.size; r++) {
    const rowDiv = document.createElement("div");
    rowDiv.className = "gomoku-row";
    for (let c = 0; c < s.size; c++) {
      const value = s.board[r * s.size + c];
      const key = `${r},${c}`;
      const cell = document.createElement("button");
      cell.type = "button";
      cell.className = "gomoku-cell";
      if (s.last_move && s.last_move[0] === r && s.last_move[1] === c) cell.classList.add("last-move");
      const legal = isMyTurn && legalSet.has(key);
      cell.disabled = !legal;
      if (legal) cell.classList.add("legal");
      if (value !== 0) {
        const stone = document.createElement("span");
        stone.className = "stone " + (value === 1 ? "black" : "white");
        cell.appendChild(stone);
      }
      cell.onclick = () => {
        if (legal) ws.send(JSON.stringify({ type: "play", action: key }));
      };
      rowDiv.appendChild(cell);
    }
    boardDiv.appendChild(rowDiv);
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
