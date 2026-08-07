let ws = null;
let mySeat = null;
let selectedForComm = null;
let lastState = null;

const suitClass = (code) => ({ Y: "yellow", P: "pink", G: "green", B: "blue", S: "submarine" }[code[0]] || "");

function el(id) { return document.getElementById(id); }
function show(id) { el(id).classList.remove("hidden"); }
function hide(id) { el(id).classList.add("hidden"); }

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
    renderState(msg);
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

function cardEl(code, { clickable, selected } = {}) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = `card ${suitClass(code)}` + (clickable ? "" : " disabled") + (selected ? " selected" : "");
  btn.textContent = code;
  btn.disabled = !clickable;
  return btn;
}

function renderState(s) {
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
  el("turnIndicator").textContent =
    s.player_to_act === null ? "게임 종료" : isMyTurn ? "당신 차례" : `P${s.player_to_act} 차례 대기`;

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
        ws.send(JSON.stringify({ type: "play", card: code }));
        selectedForComm = null;
      } else if (commOnly) {
        selectedForComm = selectedForComm === code ? null : code;
        renderState(lastState);
      }
    };
    handDiv.appendChild(card);
  });

  el("commBtn").disabled = !(s.can_communicate && selectedForComm);
  el("commBtn").onclick = () => {
    if (selectedForComm) {
      ws.send(JSON.stringify({ type: "communicate", card: selectedForComm }));
      selectedForComm = null;
    }
  };
}

el("createBtn").onclick = async () => {
  const num_players = parseInt(el("np").value, 10);
  const difficulty = parseInt(el("diff").value, 10);
  const res = await fetch("/api/rooms", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ num_players, difficulty }),
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

el("addAiBtn").onclick = () => ws.send(JSON.stringify({ type: "add_ai" }));
el("startBtn").onclick = () => ws.send(JSON.stringify({ type: "start" }));
