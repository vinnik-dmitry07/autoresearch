const $ = (sel) => document.querySelector(sel);

const RANK_LABEL = { T: '10' };

function rankLabel(rank) {
  return RANK_LABEL[rank] || rank;
}

function cardEl(c, { mini = false, onclick = null, selected = false, disabled = false } = {}) {
  const el = document.createElement('div');
  el.className = 'card' + (c.red ? ' red' : '') + (c.trump ? ' trump-card' : '') +
    (mini ? ' mini' : '') + (selected ? ' selected' : '') + (disabled ? ' disabled' : '');
  el.innerHTML = `<span class="rank">${rankLabel(c.rank)}</span><span class="suit">${c.sym}</span>`;
  if (onclick && !disabled) el.addEventListener('click', onclick);
  return el;
}

function renderCardBacks(count) {
  const row = $('#opp-hand');
  row.replaceChildren();
  const n = Math.min(Math.max(count, 1), 8);
  for (let i = 0; i < n; i += 1) {
    const b = document.createElement('div');
    b.className = 'card-back';
    row.appendChild(b);
  }
}

function renderHand(state) {
  const row = $('#your-hand');
  row.replaceChildren();
  const playable = new Set(
    state.waitingHuman
      ? state.legalMoves.filter((m) => m.card).map((m) => m.card.id)
      : [],
  );

  state.hand.forEach((c) => {
    const canPlay = playable.has(c.id);
    row.appendChild(cardEl(c, {
      disabled: state.waitingHuman && !canPlay,
      onclick: canPlay ? () => playMoveByCard(state, c.id) : null,
    }));
  });
}

function renderTable(state) {
  const table = $('#table');
  table.replaceChildren();
  if (!state.table.length) {
    const empty = document.createElement('div');
    empty.className = 'status-banner';
    empty.textContent = 'Table is empty';
    table.appendChild(empty);
    return;
  }
  state.table.forEach((pair) => {
    const wrap = document.createElement('div');
    wrap.className = 'pair';
    wrap.appendChild(cardEl(pair.attack));
    if (pair.defense) {
      const def = cardEl(pair.defense);
      def.classList.add('defense');
      wrap.appendChild(def);
    }
    table.appendChild(wrap);
  });
}

function renderActions(state) {
  const box = $('#actions');
  box.replaceChildren();
  if (!state.waitingHuman) return;

  state.legalMoves.forEach((m) => {
    const btn = document.createElement('button');
    btn.className = 'action-btn' + (m.type === 'take' ? '' : ' primary');
    btn.textContent = m.label;
    btn.addEventListener('click', () => sendMove(m.index));
    box.appendChild(btn);
  });
}

function renderLog(lines) {
  const log = $('#log');
  log.replaceChildren();
  lines.slice(-40).forEach((line) => {
    const li = document.createElement('li');
    li.textContent = line;
    log.appendChild(li);
  });
}

function roleText(state) {
  if (state.gameOver) return '—';
  if (!state.waitingHuman) return state.youAttack ? 'attacking' : 'defending';
  return state.role === 'attack' ? 'your turn — attack' : 'your turn — defend';
}

function render(state) {
  $('#deck-count').textContent = state.deck;
  $('#opp-count').textContent = state.opponentCards;
  $('#trump-card').replaceChildren(cardEl(state.trump, { mini: true }));
  $('#role').textContent = roleText(state);
  $('#your-role').textContent = state.youAttack ? 'attack' : 'defense';

  renderCardBacks(state.opponentCards);
  renderTable(state);
  renderHand(state);
  renderActions(state);
  renderLog(state.log);

  if (state.gameOver) {
    const titles = { win: 'Victory!', loss: 'You lost', draw: 'Draw' };
    const texts = {
      win: 'You were the first to get rid of all your cards.',
      loss: 'Agent B2 was stronger in this game.',
      draw: 'Both hands emptied at the same time.',
    };
    $('#result-title').textContent = titles[state.result] || 'Game over';
    $('#result-text').textContent = texts[state.result] || '';
    $('#overlay').classList.remove('hidden');
    $('#status').textContent = titles[state.result] || 'Game over';
  } else {
    $('#overlay').classList.add('hidden');
    $('#status').textContent = state.waitingHuman
      ? (state.role === 'attack' ? 'Choose a card to attack or end your turn' : 'Defend with a card or take')
      : 'AI is thinking…';
  }
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

function randomSeed() {
  const buf = new Uint32Array(1);
  crypto.getRandomValues(buf);
  return buf[0];
}

function resolveSeed(raw) {
  if (!raw) return { seed: randomSeed(), random: true };
  const n = Number(raw);
  if (!Number.isFinite(n) || n < 0) return { seed: randomSeed(), random: true };
  return { seed: Math.trunc(n), random: false };
}

async function newGame() {
  const input = $('#seed');
  const { seed, random } = resolveSeed(input.value.trim());
  const state = await api('/api/new', {
    method: 'POST',
    body: JSON.stringify({ seed }),
  });
  if (state.seed != null) input.value = String(state.seed);
  else if (random) input.value = String(seed);
  render(state);
}

async function sendMove(index) {
  const state = await api('/api/move', { method: 'POST', body: JSON.stringify({ index }) });
  render(state);
}

function playMoveByCard(state, cardId) {
  const move = state.legalMoves.find((m) => m.card && m.card.id === cardId);
  if (move) sendMove(move.index);
}

$('#new-game').addEventListener('click', newGame);
$('#play-again').addEventListener('click', newGame);

newGame().catch(() => {
  $('#status').textContent = 'Start the server: durak\\build\\web_server.exe';
});