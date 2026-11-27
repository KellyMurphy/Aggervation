// Aggravation online: home -> waiting room -> game, all driven by state pushed from the server.

const COLORS = ["RED", "GREEN", "BLUE", "YELLOW"];
const HEX = { RED: "#ed1c24", GREEN: "#009d48", BLUE: "#034ea2", YELLOW: "#ffd400" };
const SVGNS = "http://www.w3.org/2000/svg";
const HOLE_R = 15, PEG_R = 12, RING_R = 21;

const $ = (id) => document.getElementById(id);
const title = (s) => s.charAt(0) + s.slice(1).toLowerCase();
const key = (color, num) => `${color}:${num}`;

function lighten(hex, amount = 0.4) {
  const n = parseInt(hex.slice(1), 16);
  const ch = [n >> 16, (n >> 8) & 255, n & 255].map((v) => Math.round(v + (255 - v) * amount));
  return `rgb(${ch.join(",")})`;
}

// A random id kept in this browser, so refreshing the page rejoins the same seat.
const token = localStorage.aggToken || (localStorage.aggToken = Array.from(
  crypto.getRandomValues(new Uint8Array(16)), (b) => b.toString(16).padStart(2, "0")).join(""));

let layout = null;   // hole positions from the server
let state = null;    // latest state from the server
let ws = null;
let code = null;
let lastSeq = null;
let sel = freshSel();
let boardBuilt = false;

function freshSel(msg = "") {
  return { card: null, swapFrom: null, split: [], splitPeg: null, msg, pending: false };
}

// ---------- Home ----------

$("name").value = localStorage.aggName || "";

function showError(msg) {
  const id = !code ? "home-error" : state?.phase === "lobby" ? "lobby-error" : "table-error";
  $(id).textContent = msg;
}

function clearErrors() {
  for (const id of ["home-error", "lobby-error", "table-error"]) $(id).textContent = "";
}

function getName() {
  const name = $("name").value.trim();
  if (!name) {
    showError("Please enter your name first");
    $("name").focus();
    return null;
  }
  localStorage.aggName = name;
  return name;
}

function normalizeCode(text) {
  const s = (text || "").replace(/[^a-z0-9]/gi, "").toUpperCase();
  return s.length === 8 ? `${s.slice(0, 4)}-${s.slice(4)}` : null;
}

$("create").onclick = async () => {
  const name = getName();
  if (!name) return;
  const r = await fetch("/api/rooms", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token, name }),
  });
  if (!r.ok) return showError("Couldn't create a game - try again");
  enterRoom((await r.json()).code);
};

async function joinFromInput() {
  const name = getName();
  if (!name) return;
  const c = normalizeCode($("code-input").value);
  if (!c) return showError("Codes look like XU8R-D4FG");
  const r = await fetch(`/api/rooms/${c}`);
  if (!r.ok) return showError(`No game with code ${c}`);
  enterRoom(c);
}

$("join").onclick = joinFromInput;
$("code-input").addEventListener("keydown", (e) => { if (e.key === "Enter") joinFromInput(); });
$("code-input").addEventListener("input", (e) => {
  const raw = e.target.value.replace(/[^a-z0-9]/gi, "").toUpperCase().slice(0, 8);
  e.target.value = raw.length > 4 ? `${raw.slice(0, 4)}-${raw.slice(4)}` : raw;
});

// ---------- Connection ----------

function enterRoom(c) {
  code = c;
  history.replaceState(null, "", `/g/${c}`);
  connect();
}

function leaveRoom(message) {
  code = null;
  state = null;
  if (ws) ws.close();
  history.replaceState(null, "", "/");
  showScreen("home");
  if (message) showError(message);
}

function connect() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const name = encodeURIComponent(localStorage.aggName || "");
  const sock = new WebSocket(`${proto}://${location.host}/ws/${code}?token=${token}&name=${name}`);
  ws = sock;
  sock.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.type === "state") onState(msg);
    else if (msg.type === "error") {
      if (msg.fatal) leaveRoom(msg.message);
      else { sel = freshSel(); showError(msg.message); if (state) render(); }
    }
  };
  sock.onclose = () => {
    if (code && ws === sock) setTimeout(connect, 1500); // reconnect after a dropped connection
  };
}

function send(obj) {
  if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(obj));
}

function onState(s) {
  state = s;
  const seq = s.game ? s.game.turn_seq : null;
  if (seq !== lastSeq) {
    sel = freshSel();
    lastSeq = seq;
    clearErrors();
  }
  render();
}

// ---------- Rendering ----------

function showScreen(name) {
  for (const id of ["home", "lobby", "table"]) $(id).classList.toggle("hidden", id !== name);
}

function render() {
  if (!state) return;
  if (state.phase === "lobby") {
    showScreen("lobby");
    renderLobby();
  } else {
    showScreen("table");
    renderTable();
  }
}

function seatStyle(el, color) {
  el.style.setProperty("--seat", HEX[color]);
  el.style.setProperty("--seat-text", lighten(HEX[color]));
}

function renderLobby() {
  const s = state;
  $("code").textContent = s.code;
  const seats = $("seats");
  seats.innerHTML = "";
  for (const color of COLORS) {
    const seat = s.seats[color];
    const mine = s.you.seat === color;
    const row = document.createElement("div");
    row.className = "seat" + (mine ? " mine" : "");
    seatStyle(row, color);

    const who = document.createElement("div");
    who.className = "who";
    let name = seat.kind === "empty" ? "Empty seat" : seat.name;
    if (mine) name += " (you)";
    if (seat.host) name += " - host";
    if (seat.kind === "human" && !seat.connected) name += " - disconnected";
    who.innerHTML = `<span class="color">${title(color)}</span> <span class="name"></span>`;
    who.querySelector(".name").textContent = name;
    row.appendChild(who);

    const button = (label, msg) => {
      const b = document.createElement("button");
      b.textContent = label;
      b.onclick = () => send(msg);
      row.appendChild(b);
    };
    if (seat.kind === "empty" && !mine) button("Sit here", { type: "sit", seat: color });
    if (mine) button("Leave seat", { type: "stand" });
    if (s.you.host) {
      if (seat.kind === "computer") button("Remove computer", { type: "computer", seat: color, on: false });
      else if (seat.kind === "empty" || (seat.kind === "human" && !seat.connected))
        button("Add computer", { type: "computer", seat: color, on: true });
    }
    seats.appendChild(row);
  }

  $("partners").checked = s.partners;
  $("partners").disabled = !s.you.host;
  $("start").classList.toggle("hidden", !s.you.host);
  const empty = COLORS.filter((c) => s.seats[c].kind === "empty").length;
  $("lobby-note").textContent = s.you.host
    ? (empty ? `Start when everyone's here. ${empty} empty seat${empty > 1 ? "s" : ""} will be played by the computer.` : "Everyone's seated - start when ready.")
    : "Waiting for the host to start the game...";
  $("watchers").textContent = s.watchers.length ? `Watching: ${s.watchers.join(", ")}` : "";
}

$("partners").onchange = (e) => send({ type: "partners", on: e.target.checked });
$("start").onclick = () => send({ type: "start" });
$("again").onclick = () => send({ type: "lobby" });
$("copy-link").onclick = async () => {
  const url = `${location.origin}/g/${state.code}`;
  try {
    await navigator.clipboard.writeText(url);
    $("copied").textContent = "Link copied - paste it to your friends";
  } catch {
    window.prompt("Copy this link and send it to your friends:", url);
  }
};

function myTurn() {
  const g = state.game;
  return state.phase === "playing" && g && state.you.seat === g.current;
}

function seatName(color) {
  const seat = state.seats[color];
  if (state.you.seat === color) return "You";
  return seat.name || title(color);
}

function renderTable() {
  const s = state, g = s.game;
  if (!boardBuilt) buildBoard();
  applyRotation();
  drawPieces();
  $("table-code").textContent = s.code;
  document.documentElement.style.setProperty("--me", s.you.seat ? HEX[s.you.seat] : "#fff");

  // Turn line
  let turn;
  if (s.phase === "over") turn = "Game over";
  else if (myTurn()) turn = "Your turn";
  else {
    const seat = s.seats[g.current];
    turn = `${seatName(g.current)}'s turn` + (seat.kind === "computer" ? " (computer)" : "") +
      (seat.kind === "human" && !seat.connected ? " (disconnected)" : "");
  }
  if (g.control !== g.current && s.phase === "playing") turn += ` - moving ${title(g.control)}'s pegs`;
  $("turn").textContent = turn;
  $("turn").style.color = lighten(HEX[g.current], 0.3);

  // Hand
  const hand = $("hand");
  hand.innerHTML = "";
  const mine = myTurn();
  g.hand.forEach((card, i) => {
    const b = document.createElement("button");
    b.className = "playing-card" + (card.suit === "H" || card.suit === "D" ? " red-suit" : "");
    b.textContent = card.label;
    if (mine) {
      const playable = g.skip_pending || g.moves[i].length > 0;
      b.classList.add(playable ? "playable" : "dim");
      if (sel.card === i) b.classList.add("selected");
      b.onclick = () => clickCard(i);
    } else {
      b.disabled = true;
    }
    hand.appendChild(b);
  });
  if (!s.you.seat) hand.innerHTML = '<span class="hint">You\'re watching this game.</span>';

  // Prompt
  let prompt = "";
  if (mine) {
    prompt = g.skip_pending ? "Skipped by a jack! Pick a card to lay without moving."
      : sel.msg || "Pick a card, then the peg to move.";
  }
  $("prompt").textContent = prompt;

  // Game over
  $("over").classList.toggle("hidden", s.phase !== "over");
  if (s.phase === "over") {
    const names = g.winners.map((c) => `${seatName(c)} (${title(c)})`).join(" & ");
    $("winner").textContent = `${names} ${g.winners.length > 1 ? "win" : "wins"}!`;
    $("winner").style.color = lighten(HEX[g.winners[0]], 0.2);
    $("again").classList.toggle("hidden", !s.you.host);
    $("again-note").textContent = s.you.host ? "" : "Waiting for the host...";
  }

  // Players
  const players = $("players");
  players.innerHTML = "";
  for (const color of COLORS) {
    const p = g.players[color], seat = s.seats[color];
    const div = document.createElement("div");
    div.className = "player" + (color === g.current && s.phase === "playing" ? " current" : "");
    seatStyle(div, color);
    const lines = [];
    let status = p.folded ? "folded" : `${p.cards} card${p.cards === 1 ? "" : "s"}`;
    if (g.winners.includes(color)) status = "winner!";
    else if (p.all_home) status += ", all home";
    if (g.dealer === color) status += ", dealer";
    lines.push(status);
    if (p.partner) lines.push(p.control !== color ? `moving ${title(p.control)}'s pegs` : `partner: ${title(p.partner)}`);
    if (seat.kind === "human" && !seat.connected) lines.push("disconnected");
    div.innerHTML = `<div class="pname"></div>` + lines.map(() => '<div class="pstat"></div>').join("");
    div.querySelector(".pname").textContent =
      `${title(color)}: ${seat.kind === "computer" ? "Computer" : seatName(color)}`;
    div.querySelectorAll(".pstat").forEach((el, i) => { el.textContent = lines[i]; });
    players.appendChild(div);
  }

  // Log, newest first
  const log = $("log");
  log.innerHTML = "";
  for (const line of g.log.slice().reverse()) {
    const li = document.createElement("li");
    li.textContent = line;
    log.appendChild(li);
  }
}

// ---------- Board ----------

const board = $("board");
let gPegs, gMarkers, root;
let rotation = 0;

// Degrees to turn the board so ``color``'s home row is at the bottom.
function rotationFor(color) {
  if (!color) return 0;
  const [w, h] = layout.viewbox;
  const home = layout.players[color].home;
  const dx = home.reduce((t, p) => t + p[0], 0) / home.length - w / 2;
  const dy = home.reduce((t, p) => t + p[1], 0) / home.length - h / 2;
  const angle = Math.atan2(dy, dx) * 180 / Math.PI; // 90 = pointing down
  return Math.round((90 - angle) / 90) * 90;
}

function applyRotation() {
  const [w, h] = layout.viewbox;
  rotation = rotationFor(state.you.seat);
  root.setAttribute("transform", `rotate(${rotation} ${w / 2} ${h / 2})`);
}

function svg(tag, attrs, parent) {
  const el = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  if (parent) parent.appendChild(el);
  return el;
}

function buildBoard() {
  const [w, h] = layout.viewbox;
  board.setAttribute("viewBox", `0 0 ${w} ${h}`);
  board.innerHTML = "";
  // Everything goes in one group so the whole board can be turned (your colour at the bottom).
  root = svg("g", {}, board);
  svg("circle", { cx: w / 2, cy: h / 2, r: Math.min(w, h) / 2, fill: "#c49a6c" }, root);
  const pts = layout.track.map(([x, y]) => `${x},${y}`).join(" ");
  svg("polygon", { points: pts, class: "track-line" }, root);
  const starts = {};
  for (const c of COLORS) starts[layout.players[c].start_index] = c;
  layout.track.forEach(([x, y], i) => {
    if (starts[i]) svg("circle", { cx: x, cy: y, r: HOLE_R + 3, fill: HEX[starts[i]], stroke: "#fff", "stroke-width": 2 }, root);
    else svg("circle", { cx: x, cy: y, r: HOLE_R, class: "hole" }, root);
  });
  for (const c of COLORS) {
    for (const [x, y] of layout.players[c].base) svg("circle", { cx: x, cy: y, r: HOLE_R, fill: "none", stroke: HEX[c], "stroke-width": 2 }, root);
    for (const [x, y] of layout.players[c].home) svg("circle", { cx: x, cy: y, r: HOLE_R, fill: "none", stroke: HEX[c], "stroke-width": 3 }, root);
  }
  gPegs = svg("g", {}, root);
  gMarkers = svg("g", {}, root);
  boardBuilt = true;
}

function holeXY(color, zone, index) {
  if (zone === "track") return layout.track[index];
  return layout.players[color][zone][index];
}

// The pegs as the player sees them: with a 7's chosen parts already moved.
function previewPegs() {
  const pegs = state.game.pegs.map((p) => ({ ...p }));
  const find = (c, n) => pegs.find((p) => p.color === c && p.num === n);
  for (const seg of sel.split) {
    for (const [c, n] of seg.sent) {
      const used = new Set(pegs.filter((q) => q.color === c && q.zone === "base").map((q) => q.index));
      let slot = 0;
      while (used.has(slot)) slot++;
      Object.assign(find(c, n), { zone: "base", index: slot, blocking: false });
    }
    Object.assign(find(seg.color, seg.num), { zone: seg.dest.zone, index: seg.dest.index, blocking: false });
  }
  return pegs;
}

function drawPieces() {
  const g = state.game;
  gPegs.innerHTML = "";
  gMarkers.innerHTML = "";
  const selectable = selectableKeys();
  const chosen = new Set();
  if (sel.swapFrom !== null) chosen.add(key(g.control, sel.swapFrom));
  if (sel.splitPeg) chosen.add(key(...sel.splitPeg));
  const last = new Set(g.last_moved.map(([c, n]) => key(c, n)));

  for (const p of previewPegs()) {
    const [x, y] = holeXY(p.color, p.zone, p.index);
    const k = key(p.color, p.num);
    if (last.has(k)) svg("circle", { cx: x, cy: y, r: RING_R + 5, class: "ring-last", stroke: HEX[p.color] }, gPegs);
    const peg = svg("circle", { cx: x, cy: y, r: PEG_R, fill: HEX[p.color], class: "peg" }, gPegs);
    if (p.blocking) { peg.setAttribute("stroke", "#231f20"); peg.setAttribute("stroke-width", 5); }
    svg("circle", { cx: x - 4, cy: y - 4, r: 3, fill: "#fff", "pointer-events": "none" }, gPegs);
    if (chosen.has(k)) svg("circle", { cx: x, cy: y, r: RING_R, class: "ring-chosen" }, gPegs);
    else if (selectable.has(k)) svg("circle", { cx: x, cy: y, r: RING_R, class: "ring-select" }, gPegs);
    if (selectable.has(k) || chosen.has(k)) {
      peg.classList.add("clickable");
      // A bigger invisible target makes pegs easy to tap on phones.
      const hit = svg("circle", { cx: x, cy: y, r: RING_R + 6, fill: "transparent", class: "peg clickable" }, gPegs);
      hit.style.stroke = "none";
      hit.onclick = () => clickPeg(p.color, p.num);
    }
  }

  for (const [steps, seg] of splitOptions()) {
    const [x, y] = holeXY(seg.color, seg.dest.zone, seg.dest.index);
    const m = svg("g", { class: "marker" }, gMarkers);
    svg("circle", { cx: x, cy: y, r: RING_R, stroke: HEX[seg.color] }, m);
    const t = svg("text", { x, y: y + 6, "text-anchor": "middle", transform: `rotate(${-rotation} ${x} ${y})` }, m);
    t.textContent = steps;
    m.onclick = () => chooseSteps(steps);
  }
}

// ---------- Choosing a play: card, then peg(s) ----------

const cardMoves = () => (sel.card === null ? [] : state.game.moves[sel.card]);
const cardRank = () => state.game.hand[sel.card].rank;
const sameSeg = (a, b) => a.color === b.color && a.num === b.num && a.steps === b.steps;

function continuations() {
  const n = sel.split.length;
  return cardMoves().filter((m) => m.segments.length > n && sel.split.every((s, i) => sameSeg(s, m.segments[i])));
}

function selectableKeys() {
  const set = new Set();
  if (!myTurn() || sel.card === null) return set;
  const g = state.game, ctl = g.control, moves = cardMoves(), rank = cardRank();
  if (rank === "10") {
    if (sel.swapFrom === null) moves.forEach((m) => set.add(key(ctl, m.peg)));
    else moves.filter((m) => m.peg === sel.swapFrom).forEach((m) => set.add(key(m.target[0], m.target[1])));
    return set;
  }
  if (rank === "7") {
    if (sel.splitPeg) return set;
    const n = sel.split.length;
    continuations().forEach((m) => set.add(key(m.segments[n].color, m.segments[n].num)));
    return set;
  }
  moves.forEach((m) => { if (m.peg !== null) set.add(key(ctl, m.peg)); });
  if (moves.some((m) => m.kind === "enter")) {
    g.pegs.filter((p) => p.color === ctl && p.zone === "base").forEach((p) => set.add(key(p.color, p.num)));
  }
  return set;
}

function splitOptions() {
  const opts = new Map();
  if (!sel.splitPeg || !myTurn()) return opts;
  const n = sel.split.length, [c, num] = sel.splitPeg;
  for (const m of continuations()) {
    const seg = m.segments[n];
    if (seg.color === c && seg.num === num && !opts.has(seg.steps)) opts.set(seg.steps, seg);
  }
  return new Map([...opts.entries()].sort((a, b) => a[0] - b[0]));
}

function promptFor() {
  if (sel.card === null) return "";
  const rank = cardRank();
  if (rank === "10") return "10: click your peg to swap";
  if (rank === "7") {
    const left = 7 - sel.split.reduce((t, s) => t + s.steps, 0);
    return `7: click a peg to move (${left} step${left === 1 ? "" : "s"} left)`;
  }
  return `${state.game.hand[sel.card].label}: click the peg to move`;
}

function sendPlay(card, move) {
  // Ignore further clicks until the server answers (a new state, or an error).
  send({ type: "play", card, move, turn_seq: state.game.turn_seq });
  sel.pending = true;
  sel.msg = "Sending...";
  render();
}

function clickCard(i) {
  if (!myTurn() || sel.pending) return;
  const g = state.game;
  if (g.skip_pending) return sendPlay(i, null);
  if (sel.card === i) sel = freshSel();
  else if (!g.moves[i].length) sel = freshSel(`${g.hand[i].label} can't move right now - pick another card`);
  else {
    sel = freshSel();
    sel.card = i;
    sel.msg = promptFor();
  }
  render();
}

function clickPeg(color, num) {
  if (sel.pending) return;
  if (sel.splitPeg && sel.splitPeg[0] === color && sel.splitPeg[1] === num) {
    sel.splitPeg = null;
    sel.msg = promptFor();
    return render();
  }
  if (!selectableKeys().has(key(color, num))) return;
  const g = state.game, moves = cardMoves(), rank = cardRank();
  if (rank === "10") {
    if (sel.swapFrom === null) {
      sel.swapFrom = num;
      sel.msg = "Now click the peg to swap places with";
      return render();
    }
    return sendPlay(sel.card, moves.findIndex((m) => m.peg === sel.swapFrom && m.target[0] === color && m.target[1] === num));
  }
  if (rank === "7") {
    sel.splitPeg = [color, num];
    const opts = splitOptions();
    if (opts.size === 1) return chooseSteps([...opts.keys()][0]);
    sel.msg = "Click where this peg goes (or press the number)";
    return render();
  }
  const peg = g.pegs.find((p) => p.color === color && p.num === num);
  const idx = peg.zone === "base"
    ? moves.findIndex((m) => m.kind === "enter")
    : moves.findIndex((m) => m.peg === num && m.kind !== "enter");
  sendPlay(sel.card, idx);
}

function chooseSteps(steps) {
  if (sel.pending) return;
  const opts = splitOptions();
  if (!opts.has(steps)) return;
  sel.split.push(opts.get(steps));
  sel.splitPeg = null;
  const idx = cardMoves().findIndex((m) => m.segments.length === sel.split.length && sel.split.every((s, i) => sameSeg(s, m.segments[i])));
  if (idx >= 0) return sendPlay(sel.card, idx);
  sel.msg = promptFor();
  render();
}

document.addEventListener("keydown", (e) => {
  if (!state || state.phase !== "playing" || e.target.tagName === "INPUT") return;
  if (e.key === "Escape") { sel = freshSel(); render(); }
  const n = parseInt(e.key, 10);
  if (n >= 1 && n <= 9) {
    if (sel.splitPeg) chooseSteps(n);
    else clickCard(n - 1);
  }
});

// ---------- Start ----------

(async function init() {
  layout = await (await fetch("/api/layout")).json();
  const m = location.pathname.match(/^\/g\/([^/]+)/);
  const linked = m ? normalizeCode(decodeURIComponent(m[1])) : null;
  if (linked) {
    $("code-input").value = linked;
    if (localStorage.aggName) return enterRoom(linked);
    showScreen("home");
    $("name").focus();
    showError("Enter your name, then press Join");
    return;
  }
  showScreen("home");
})();
