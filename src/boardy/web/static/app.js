let ws = null;
let mySeat = null;
let lastState = null;
let games = [];
// Trick number for which the "확인" step (reviewing the just-finished
// trick) has been done -- either clicked, or skipped because there was
// nothing to review (trick 1). Communication/준비 UI only shows once this
// matches the current trick_ready window's trick number (see renderReady).
let trickReadyAckedFor = null;
// Trick number for which we've already auto-sent "ready" because this
// seat isn't going to communicate this window -- either it has no token
// left, or it has one but never armed it (see commArmed below). Avoids
// resending on every re-render while waiting for the server's ack.
let autoReadySentFor = null;
// Client-only "I want to use my Sonar token before the next trick" intent
// flag, set by pressing the persistent commTokenWidget button (see
// renderCommWidget) -- can be pressed any time, not just during the
// trick_ready window itself. Only when this is true *and* a trick_ready
// window is actually open does renderReady show the card/marker picker;
// otherwise the window auto-clears itself with no click required. Cleared
// after the token is actually spent, "그냥 안 쓸래요" is pressed, or a new
// room/game starts.
let commArmed = false;
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
  el("helperLabel").classList.toggle("hidden", g.slug !== "deep_sea_crew");
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

// Polls /api/rooms/{code} while the seat picker is up so a seat someone
// else just claimed shows as taken here too, instead of a stale snapshot
// from the moment this screen opened -- otherwise two people looking at
// the picker at the same time could both think an already-taken seat is
// free and race for it.
let seatPickerInterval = null;
// Remembered so a failed seat claim (lost a race to someone else who
// clicked the same seat first -- server rejects with "error") can resume
// the picker instead of leaving it frozen on the stale pre-click state.
let seatPickerCode = null;
let seatPickerName = null;

function stopSeatPickerPolling() {
  if (seatPickerInterval !== null) {
    clearInterval(seatPickerInterval);
    seatPickerInterval = null;
  }
}

function renderSeatButtons(code, name, info) {
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
      stopSeatPickerPolling();
      if (lastSetup) lastSetup.seat = i;
      connect(code, name, i);
    };
    container.appendChild(btn);
  });
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
  seatPickerCode = code;
  seatPickerName = name;
  renderSeatButtons(code, name, info);

  stopSeatPickerPolling();
  seatPickerInterval = setInterval(async () => {
    let fresh;
    try {
      fresh = await (await fetch(`/api/rooms/${code}`)).json();
    } catch {
      return; // transient network hiccup -- just try again next tick
    }
    if (fresh.error) {
      stopSeatPickerPolling();
      return;
    }
    renderSeatButtons(code, name, fresh);
  }, 1500);
}

function handleMessage(msg) {
  if (msg.type === "error") {
    alert(msg.message);
    // If this happened while claiming a seat (e.g. lost a race to
    // someone else who grabbed it first -- see the "seat taken" case in
    // server.py's ws handler), the picker is still open but now stale;
    // refresh it instead of leaving it stuck on the pre-click snapshot.
    if (seatPickerCode && !el("seatPicker").classList.contains("hidden")) {
      showSeatPicker(seatPickerCode, seatPickerName);
    }
    return;
  }
  // Any other real message means we're already connected -- definitely
  // past picking a seat, regardless of which code path got us here.
  stopSeatPickerPolling();
  if (msg.type === "joined") {
    mySeat = msg.seat;
    trickReadyAckedFor = null;
    autoReadySentFor = null;
    commArmed = false;
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
    // NOT `player_to_act === null` -- that's also true for Deep Sea Crew's
    // "trick_ready" window (nobody has an exclusive turn while everyone
    // readies up between tricks, see engine.py's player_to_act), which
    // made the "다시 플레이/홈으로 돌아가기" buttons flash up after every
    // single trick, not just when the game actually ended. Each game
    // exposes its own real terminal marker instead (see GameSpec.outcome).
    const gameOver = msg.game === "gomoku" ? msg.winner !== null : msg.outcome !== null;
    if (gameOver) {
      show("postGameControls");
    } else {
      hide("postGameControls");
    }
    return;
  }
}

el("homeBtn").onclick = () => {
  stopSeatPickerPolling();
  if (ws) {
    ws.onclose = null;
    ws.close();
    ws = null;
  }
  lastState = null;
  mySeat = null;
  trickReadyAckedFor = null;
  autoReadySentFor = null;
  commArmed = false;
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

// Renders a completed TrickRecord (from s.history) into `container`, in
// actual play order rather than seat order. Shared by the trick_ready
// review screen and the post-game "what happened on the final trick" view.
function renderTrickRecord(container, record, numPlayers) {
  container.innerHTML = "";
  const heading = document.createElement("b");
  heading.textContent = `트릭 #${record.number} - P${record.winner} 승리!`;
  container.appendChild(heading);
  container.appendChild(document.createElement("br"));
  for (const seat of playOrderFor(record.leader, numPlayers)) {
    if (seat in record.cards) container.appendChild(trickCardSpan(seat, record.cards[seat], seat == record.winner));
  }
}

const CARD_HELPER_SUITS = ["yellow", "pink", "green", "blue", "submarine"];
const CARD_HELPER_LABEL_KO = { yellow: "노랑", pink: "분홍", green: "초록", blue: "파랑", submarine: "잠수함" };
const CARD_HELPER_CODE = { yellow: "Y", pink: "P", green: "G", blue: "B", submarine: "S" };

// Optional display aid: a 5-row (4 colors + submarine) table of every
// card, with the ones already seen (played, in any completed or
// in-progress trick) highlighted. Opt-in via #cardHelperToggle when
// creating a room (see createBtn) -- a room-wide setting the server
// broadcasts to every seat (s.card_helper), not a per-client preference,
// so everyone sees the same thing regardless of who created the room.
function renderCardHelper(s) {
  const container = el("cardHelperTable");
  if (!s.card_helper) {
    hide("cardHelperTable");
    return;
  }
  show("cardHelperTable");

  const seen = new Set();
  s.history.forEach((rec) => Object.values(rec.cards).forEach((code) => seen.add(code)));
  Object.values(s.trick_in_progress).forEach((code) => seen.add(code));

  container.innerHTML = "";
  const heading = document.createElement("div");
  heading.className = "hint";
  heading.textContent = "카드 도우미 (지금까지 나온 카드)";
  container.appendChild(heading);

  const table = document.createElement("table");
  table.className = "card-helper";
  CARD_HELPER_SUITS.forEach((suit) => {
    const row = document.createElement("tr");
    const label = document.createElement("th");
    label.textContent = CARD_HELPER_LABEL_KO[suit];
    row.appendChild(label);
    const maxRank = suit === "submarine" ? 4 : 9;
    for (let rank = 1; rank <= 9; rank++) {
      const cell = document.createElement("td");
      if (rank <= maxRank) {
        const code = `${CARD_HELPER_CODE[suit]}${rank}`;
        cell.textContent = rank;
        cell.className = `card-helper-cell ${suit} ` + (seen.has(code) ? "seen" : "unseen");
      }
      row.appendChild(cell);
    }
    table.appendChild(row);
  });
  container.appendChild(table);
}

// ---------- round table (seat pods + trick-in-progress slots) ----------
// See docs discussion: players wanted a poker-table feel (own hand at the
// bottom, everyone else seated around a table, cards visibly "played" in
// front of each seat) instead of a flat list of stat rows, with every
// player's mission cards genuinely readable -- this is a cooperative game,
// so knowing teammates' missions is core, not something to hide.

// Angle (degrees, 0 = top/12-o'clock, clockwise) for the seat `relIndex`
// steps clockwise from "me", spacing all `n` seats evenly with relIndex 0
// (me) fixed at the bottom. Works for any player count 2-5.
function seatAngleDeg(relIndex, n) {
  return (180 + relIndex * (360 / n)) % 360;
}
function seatOffset(relIndex, n, radius) {
  const rad = (seatAngleDeg(relIndex, n) * Math.PI) / 180;
  return { x: Math.round(radius * Math.sin(rad)), y: Math.round(-radius * Math.cos(rad)) };
}

function captainBadge() {
  const b = document.createElement("span");
  b.className = "badge-captain";
  b.title = "선장 (사령관) -- 잠수함4를 받아 이번 판 내내 고정";
  b.innerHTML =
    '<svg width="11" height="11" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="5" r="2.3" stroke="currentColor" stroke-width="1.8"/><line x1="12" y1="7.3" x2="12" y2="19" stroke="currentColor" stroke-width="1.8"/><line x1="7" y1="10" x2="17" y2="10" stroke="currentColor" stroke-width="1.8"/><path d="M5 14a7 7 0 0 0 14 0" stroke="currentColor" stroke-width="1.8" fill="none"/></svg> 선장';
  return b;
}
function leaderBadge() {
  const b = document.createElement("span");
  b.className = "badge-leader";
  b.title = "이번 트릭을 리드함 (트릭마다 바뀜)";
  b.innerHTML =
    '<svg width="9" height="9" viewBox="0 0 24 24" fill="none"><path d="M5 12h13M13 6l6 6-6 6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg> 리드';
  return b;
}
function tokenBadge(available) {
  const b = document.createElement("span");
  b.className = "badge-token" + (available ? "" : " used");
  b.title = available ? "통신 토큰 남음" : "통신 토큰 이미 사용함";
  const slash = available ? "" : '<line x1="4" y1="20" x2="20" y2="4" stroke="currentColor" stroke-width="1.6"/>';
  b.innerHTML = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="2" fill="currentColor"/><path d="M8.2 8.2a5.6 5.6 0 0 1 7.6 0" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/><path d="M5 5a10 10 0 0 1 14 0" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" opacity=".55"/>${slash}</svg>`;
  return b;
}

function trickPileEl(count) {
  const pile = document.createElement("div");
  pile.className = "trick-pile" + (count === 0 ? " empty" : "");
  const layers = Math.min(count, 3);
  for (let k = 0; k < layers; k++) {
    const leaf = document.createElement("div");
    leaf.className = "leaf";
    pile.appendChild(leaf);
  }
  const badge = document.createElement("div");
  badge.className = "count";
  badge.textContent = count;
  pile.appendChild(badge);
  return pile;
}

// One mission card -- describe_plain is already correctly redacted
// server-side for a private prediction that isn't this viewer's own
// (see tasks.py's Task.describe_for), so this only needs to style that
// case differently, not compute the redaction itself.
function missionCardEl(t) {
  const wrap = document.createElement("div");
  const statusClass = t.hidden ? "" : t.resolved ? (t.success ? " done" : " failed") : "";
  wrap.className = "mission-card" + statusClass + (t.hidden ? " hidden-card" : "");
  const diff = document.createElement("div");
  diff.className = "mission-diff";
  diff.textContent = t.difficulty;
  wrap.appendChild(diff);
  const body = document.createElement("div");
  const text = document.createElement("div");
  text.className = "mission-text";
  text.textContent = t.describe_plain;
  body.appendChild(text);
  const status = document.createElement("div");
  status.className = "mission-status" + statusClass;
  status.textContent = t.hidden ? "본인만 확인 가능" : t.resolved ? (t.success ? "완료" : "실패") : "진행 중";
  body.appendChild(status);
  wrap.appendChild(body);
  return wrap;
}

const TABLE_POD_RADIUS = 250; // px from table center to each seat pod
const TABLE_CARD_RADIUS = 110; // px from table center to that seat's played-card slot

function seatPodEl(s, seat) {
  const isMe = seat === s.seat;
  const pod = document.createElement("div");
  pod.className = "seat-pod" + (s.player_to_act === seat ? " to-act" : "") + (isMe ? " me" : "");

  const head = document.createElement("div");
  head.className = "pod-head";
  const avatar = document.createElement("div");
  avatar.className = "avatar";
  head.appendChild(avatar);
  const nameWrap = document.createElement("div");
  nameWrap.style.flex = "1";
  nameWrap.style.minWidth = "0";
  const name = document.createElement("div");
  name.className = "name";
  const meta = s.players[seat] || {};
  name.textContent = `P${seat}${isMe ? " (나)" : ""}${meta.name ? " " + meta.name : ""}`;
  nameWrap.appendChild(name);
  head.appendChild(nameWrap);
  // MY own token gets a big separate CTA below the table (#commTokenWidget)
  // instead of this passive badge -- everyone else's is informational only.
  if (!isMe) head.appendChild(tokenBadge(s.tokens_available[seat]));
  pod.appendChild(head);

  const badges = document.createElement("div");
  badges.className = "pod-badges";
  if (seat === s.commander) badges.appendChild(captainBadge());
  if ((s.phase === "playing" || s.phase === "trick_ready") && seat === s.current_leader) {
    badges.appendChild(leaderBadge());
  }
  if (s.phase === "trick_ready" && s.ready_seats.includes(seat)) {
    const ready = document.createElement("span");
    ready.textContent = "✅";
    ready.title = "다음 트릭 준비 완료";
    badges.appendChild(ready);
  }
  if (badges.childNodes.length) pod.appendChild(badges);

  pod.appendChild(trickPileEl(s.tricks_won[seat]));

  // Everyone's missions are readable -- seeing teammates' missions is
  // core to this cooperative game. Mine show bigger, right above my
  // hand instead (see #myMissions), so skip them in my own pod.
  if (!isMe) {
    const missions = s.tasks.filter((t) => t.owner === seat);
    if (missions.length) {
      const row = document.createElement("div");
      row.className = "mission-row";
      missions.forEach((t) => row.appendChild(missionCardEl(t)));
      pod.appendChild(row);
    }
  }

  const sig = s.signals[seat];
  if (sig) {
    const sigWrap = cardWithToken(cardEl(sig.card, { clickable: false }), sig.marker);
    sigWrap.classList.add("signal-slot");
    pod.appendChild(sigWrap);
  }

  return pod;
}

// The table pauses at "확인" (in place of the trick-number marker) at the
// start of every trick_ready window, until this seat clicks it -- both
// when reviewing the trick that just finished (cards stay exactly where
// they were played, winner's card already picked out in gold via
// .winner-card, so the button doesn't need to repeat who won in words)
// and on the very first trick, before anyone's played a card yet, which
// otherwise had no natural pause for a player to notice they could use
// their Sonar token before committing to trick 1 (see renderReady).
function renderTable(s) {
  const circle = el("tableCircle");
  circle.innerHTML = "";

  const lastTrick = s.history.length ? s.history[s.history.length - 1] : null;
  const paused = s.phase === "trick_ready" && trickReadyAckedFor !== s.trick_number;

  for (let k = 0; k < s.num_players; k++) {
    const seat = (s.seat + k) % s.num_players;
    const podOffset = seatOffset(k, s.num_players, TABLE_POD_RADIUS);
    const pod = seatPodEl(s, seat);
    pod.style.left = `calc(50% + ${podOffset.x}px)`;
    pod.style.top = `calc(50% + ${podOffset.y}px)`;
    circle.appendChild(pod);

    let code = null;
    let isWinner = false;
    let waitingText = null;
    let waitingIsNext = false;
    if (paused && lastTrick) {
      code = lastTrick.cards[seat] ?? null;
      isWinner = seat === lastTrick.winner;
    } else if (s.phase === "playing") {
      if (seat in s.trick_in_progress) {
        code = s.trick_in_progress[seat];
      } else {
        waitingIsNext = seat === s.player_to_act;
        waitingText = waitingIsNext ? (seat === s.seat ? "차례" : "생각 중") : "대기";
      }
    }

    if (code !== null || waitingText !== null) {
      const cardOffset = seatOffset(k, s.num_players, TABLE_CARD_RADIUS);
      const slotWrap = document.createElement("div");
      slotWrap.style.position = "absolute";
      slotWrap.style.left = `calc(50% + ${cardOffset.x}px)`;
      slotWrap.style.top = `calc(50% + ${cardOffset.y}px)`;
      slotWrap.style.transform = "translate(-50%,-50%)";
      if (code !== null) {
        const card = cardEl(code, { clickable: false });
        if (isWinner) card.classList.add("winner-card");
        slotWrap.appendChild(card);
      } else {
        const dash = document.createElement("div");
        dash.className = "table-slot-empty" + (waitingIsNext ? " waiting-for-me" : "");
        dash.textContent = waitingText;
        slotWrap.appendChild(dash);
      }
      circle.appendChild(slotWrap);
    }
  }

  if (paused) {
    const panel = document.createElement("div");
    panel.className = "table-center-review";
    const confirmBtn = document.createElement("button");
    confirmBtn.className = "primary";
    confirmBtn.textContent = "확인";
    confirmBtn.onclick = () => {
      // Keyed by s.trick_number (for the very first trick, already the
      // *upcoming* one -- see engine.py's _complete_trick incrementing it
      // past lastTrick.number) so the `paused` check above stops matching
      // next render.
      trickReadyAckedFor = s.trick_number;
      renderDeepSeaCrew(lastState);
    };
    panel.appendChild(confirmBtn);
    circle.appendChild(panel);
  } else {
    const center = document.createElement("div");
    center.className = "table-center";
    center.textContent = s.trick_number <= s.hand_size ? `트릭\n${s.trick_number}/${s.hand_size}` : "";
    center.style.whiteSpace = "pre-line";
    circle.appendChild(center);
  }
}

// My own missions -- bigger, right above my hand (see #myMissions in
// index.html and the .mission-card sizing in style.css).
function renderMyMissions(s) {
  const container = el("myMissions");
  container.innerHTML = "";
  s.tasks.filter((t) => t.owner === s.seat).forEach((t) => container.appendChild(missionCardEl(t)));
}

// 예측 (prediction) task cards don't draft with a single click -- the
// drafting player has to pick a number of tricks first (see engine.py's
// GameState.draft_task, which requires a `prediction` for these). Renders
// an inline number input + confirm button instead of a plain draft-task
// button; sending "task-id:n" (see games/deep_sea_crew/spec.py's `_play`).
function renderPredictionTask(t, pickable, handSize) {
  const wrap = document.createElement("div");
  wrap.className = "draft-task predict-task" + (pickable ? " pickable" : "");

  const label = document.createElement("div");
  const visibility = t.public ? "공개" : "비공개";
  label.innerHTML = `<span class="diff">난이도 ${t.difficulty}</span>${t.describe} <em>(${visibility})</em>`;
  wrap.appendChild(label);

  if (pickable) {
    const row = document.createElement("div");
    row.className = "predict-row";

    const input = document.createElement("input");
    input.type = "number";
    input.min = "0";
    input.max = String(handSize);
    input.value = "0";
    input.className = "predict-input";

    const confirmBtn = document.createElement("button");
    confirmBtn.textContent = "이 숫자로 예측하기";
    confirmBtn.onclick = () => {
      let n = parseInt(input.value, 10);
      if (Number.isNaN(n)) n = 0;
      n = Math.max(0, Math.min(handSize, n));
      ws.send(JSON.stringify({ type: "play", action: `${t.id}:${n}` }));
    };

    row.appendChild(input);
    row.appendChild(confirmBtn);
    wrap.appendChild(row);
  }

  return wrap;
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
    const pickable = isMyTurn && s.legal_moves.includes(t.id);
    if (t.is_prediction) {
      pool.appendChild(renderPredictionTask(t, pickable, s.hand_size));
      return;
    }
    const btn = document.createElement("button");
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
// 1. Every trick_ready window opens paused -- cards from the trick that
//    just finished stay at each seat's slot (winner picked out in gold),
//    or on the very first trick, an otherwise-empty table -- with "확인"
//    sitting at the table's own center (see renderTable's `paused`
//    branch). Nothing to do here until that's clicked. This deliberate
//    pause on trick 1 too is what gives a player a moment to notice they
//    could use their Sonar token before the first card is even played --
//    without it the window would auto-ready itself before anyone had a
//    chance to react.
// 2. Once acknowledged: this seat auto-readies with no click needed,
//    UNLESS it armed the persistent token widget (commArmed, see
//    renderCommWidget) -- only then does the card/marker picker open,
//    matching what the server actually enforces (communication is only
//    legal in this exact window, before this seat has marked ready --
//    see GameState.communicate).
function renderReady(s) {
  const paused = trickReadyAckedFor !== s.trick_number;

  if (paused) {
    el("readyStatus").textContent = s.history.length
      ? "트릭 결과를 확인하세요 (테이블 가운데 → 확인)"
      : "통신 토큰을 쓰고 싶다면 지금이 기회예요 (테이블 가운데 → 확인)";
    hide("readyBlock");
    return;
  }

  const amReady = s.ready_seats.includes(s.seat);
  const notReady = [];
  for (let i = 0; i < s.num_players; i++) {
    if (!s.ready_seats.includes(i)) notReady.push(`P${i}`);
  }

  if (amReady) {
    // Nothing left for this seat to decide this window.
    el("readyStatus").textContent = notReady.length ? `대기 중: ${notReady.join(", ")}` : "모두 결정 완료";
    hide("readyBlock");
    return;
  }

  // Only open the card/marker picker if this seat can actually still
  // communicate *and* pressed the persistent token widget (commArmed --
  // see renderCommWidget) to say they want to before this trick. Anyone
  // who didn't press it just sails through with no click required --
  // this is the default for the vast majority of tricks, where nobody's
  // signaling anything.
  const showPicker = s.can_communicate && commArmed;
  if (!showPicker) {
    el("readyStatus").textContent = "다음 트릭으로 넘어가는 중...";
    hide("readyBlock");
    // Guarded by trick number so a re-render (e.g. another player's
    // broadcast) doesn't resend every time while waiting for the
    // server's ack (mark_ready is idempotent anyway, but no need to spam it).
    if (autoReadySentFor !== s.trick_number) {
      autoReadySentFor = s.trick_number;
      ws.send(JSON.stringify({ type: "ready" }));
    }
    return;
  }

  el("readyStatus").textContent = "\u{1F4E1} 통신할 카드를 고르세요 (안 쓰려면 아래 버튼)";
  show("readyBlock");

  const handDiv = el("readyHand");
  handDiv.innerHTML = "";
  s.hand.forEach((code) => {
    const marker = cardMarker(code, s.hand);
    const commOnly = marker !== null;
    const card = cardEl(code, { clickable: commOnly });
    card.title = commOnly ? `클릭해서 통신 토큰 놓기 (${MARKER_LABEL_KO[marker]})` : "";
    card.onclick = () => {
      if (commOnly) {
        commArmed = false;
        ws.send(JSON.stringify({ type: "communicate", action: code }));
      }
    };
    handDiv.appendChild(commOnly ? cardWithToken(card, marker) : card);
  });

  el("declineCommBtn").onclick = () => {
    commArmed = false;
    renderReady(lastState);
  };
}

function renderPlaying(s) {
  const table = el("table");
  // The trick currently in progress is now shown live on the round table
  // (see renderTable's per-seat card slots + its center trick-number
  // marker) -- #table only needs to handle the one case that isn't part
  // of that live view: the game ending mid-trick, which never gets its
  // own "확인" review screen (see engine.py's _complete_trick only
  // entering "trick_ready" when outcome is still None). Without this the
  // table would go blank right when it matters most: seeing exactly
  // which cards caused a mission failure. Left showing permanently.
  const lastTrick = s.history.length ? s.history[s.history.length - 1] : null;
  const inProgress = Object.keys(s.trick_in_progress).length > 0;
  if (s.outcome !== null && lastTrick && !inProgress) {
    renderTrickRecord(table, lastTrick, s.num_players);
  } else {
    table.innerHTML = "";
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

// Persistent Sonar-token button (see commArmed above): visible any time
// this seat's one-time token is unspent and the draft is over, in every
// phase -- not just during the trick_ready window -- so a player can
// decide "I want to signal before the next trick" whenever they think of
// it, instead of having to catch a narrow window. Pressing it just flips
// the intent flag and re-renders locally; it's renderReady that actually
// decides whether a trick_ready window right now should show the picker.
function renderCommWidget(s) {
  if (s.phase === "task_draft" || !s.token_available || s.outcome !== null) {
    hide("commTokenWidget");
    return;
  }
  show("commTokenWidget");
  const btn = el("commTokenBtn");
  btn.classList.toggle("armed", commArmed);
  btn.textContent = commArmed
    ? "📡 통신 예약됨 (누르면 취소)"
    : "📡 통신 토큰 사용하기";
  btn.onclick = () => {
    commArmed = !commArmed;
    renderDeepSeaCrew(lastState);
  };
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

  renderTable(s);
  renderMyMissions(s);
  renderCardHelper(s);
  renderCommWidget(s);

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
const FORBIDDEN_LABEL_KO = { double_three: "쌍삼", double_four: "쌍사", overline: "장목(6목 이상)" };

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
      const forbiddenReason = isMyTurn ? s.forbidden_reasons[key] : undefined;
      // legal implies it's my turn, so s.my_color is the acting player's
      // color here -- highlight legal points in that color, not always white.
      const point = document.createElement("button");
      point.type = "button";
      point.className = "gomoku-point" + (legal ? ` legal turn-${s.my_color}` : forbiddenReason ? " forbidden" : "");
      point.style.left = `${GOMOKU_MARGIN + c * GOMOKU_CELL}px`;
      point.style.top = `${GOMOKU_MARGIN + r * GOMOKU_CELL}px`;
      // Forbidden points stay unplayable but are still clickable (unlike
      // truly disabled ones) so clicking one can explain why, instead of
      // just silently doing nothing.
      point.disabled = !legal && !forbiddenReason;
      if (forbiddenReason) point.title = `착수 금지: ${FORBIDDEN_LABEL_KO[forbiddenReason] || forbiddenReason}`;
      if (s.last_move && s.last_move[0] === r && s.last_move[1] === c) point.classList.add("last-move");
      if (value !== 0) {
        const stone = document.createElement("span");
        stone.className = "stone " + (value === 1 ? "black" : "white");
        point.appendChild(stone);
      }
      point.onclick = () => {
        if (legal) {
          ws.send(JSON.stringify({ type: "play", action: key }));
        } else if (forbiddenReason) {
          alert(`이 자리는 금수(${FORBIDDEN_LABEL_KO[forbiddenReason] || forbiddenReason})라 둘 수 없습니다.`);
        }
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
  const card_helper = game === "deep_sea_crew" && el("cardHelperToggle").checked;
  const res = await fetch("/api/rooms", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ game, num_players, difficulty, card_helper }),
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
  lastSetup = { game, num_players, difficulty, card_helper, name, seat: null, aiModes: [] };
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
  const { game, num_players, difficulty, card_helper, name, seat, aiModes } = lastSetup;
  const res = await fetch("/api/rooms", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ game, num_players, difficulty, card_helper }),
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
  autoReadySentFor = null;
  commArmed = false;
  lastState = null;
  lastSetup = { game, num_players, difficulty, card_helper, name, seat, aiModes: [] };
  pendingAutoSetup = { aiModes };
  connect(data.code, name, seat);
};

loadGames();
