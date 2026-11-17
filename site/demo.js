/* [bracket] — the project site's simulation of the live screen, with a spotlight tour.
   Nothing here calls a model: every proposal is written out below, by hand, for each position of the dials. */
(() => {
'use strict';
const $ = s => document.querySelector(s);
const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

/* ---------------- theme ---------------- */
const themeBtn = $('#theme');
const current = () => document.documentElement.dataset.theme || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
const paintBtn = () => { themeBtn.textContent = current() === 'dark' ? 'Light' : 'Dark'; };
themeBtn.addEventListener('click', () => {
  const next = current() === 'dark' ? 'light' : 'dark';
  document.documentElement.dataset.theme = next;
  try { localStorage.setItem('bracket-theme', next); } catch (e) {}
  paintBtn();
});
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', paintBtn);
paintBtn();

/* ---------------- the hand-written option tree ----------------
   Each demo word has, for every position of the strength dial, three proposals at each length (shorter, same,
   longer) in the institutional register, and three each in the plain and formal registers. A proposal may carry the
   flags the app's check would add; "dropped" lists what the check would remove before the room saw it. */
const TREE = {
  note: { min: -1, max: 3, levels: {
    '-1': { shorter: ['see', 'mark', 'observe'], same: ['take note of', 'are aware of', 'have seen'], longer: ['have been informed of', 'are generally aware of', 'have taken account of'],
         plain: ['know about', 'see', 'have heard about'], formal: ['take cognizance of', 'are cognizant of', 'duly observe'] },
    0: { shorter: ['see', 'observe', 'mark'], same: ['observe', 'take account of', 'are aware of'], longer: ['note with interest', 'take careful note of', 'have taken note of'],
         plain: ['see', 'know about', 'are aware of'], formal: ['take note of', 'duly note', 'note for the record'] },
    1: { shorter: ['acknowledge', 'accept', 'grant'], same: ['acknowledge', 'accept', 'take stock of'], longer: ['acknowledge with appreciation', 'readily acknowledge', 'fully acknowledge'],
         plain: ['accept', 'admit', 'grant'], formal: ['acknowledge with appreciation', 'duly acknowledge', 'formally acknowledge'] },
    2: { shorter: ['recognize', 'value', 'credit'], same: ['recognize', 'appreciate', 'value'], longer: ['recognize and appreciate', 'fully recognize', 'recognize with appreciation'],
         plain: ['value', 'appreciate', 'see the worth of'], formal: ['recognize with appreciation', 'duly recognize', 'express our recognition of'] },
    3: { shorter: ['affirm', 'confirm', 'back'], same: ['affirm', 'endorse', 'confirm'], longer: ['affirm our support for', 'strongly affirm', 'affirm and endorse'],
         plain: ['back', 'support', 'stand behind'], formal: ['affirm our endorsement of', 'solemnly affirm', 'formally affirm'] },
  } },
  work: { min: -1, max: 2, levels: {
    '-1': { shorter: ['consider', 'explore', 'study'], same: ['explore', 'consider', 'look into'], longer: ['explore the possibility of', 'give consideration to', 'examine options for'],
            plain: ['think about', 'look at', 'talk about'], formal: ['give due consideration to', 'examine the feasibility of', 'consider the merits of'] },
    0: { shorter: ['seek', 'pursue', 'build'], same: ['pursue', 'seek', 'strive for'],
         longer: ['work steadily towards', 'make every effort to reach', 'work together towards'],
         plain: ['try to agree', 'aim for', 'work on'], formal: ['endeavor to achieve', 'work assiduously towards', 'seek to attain'] },
    1: { shorter: ['adopt', 'agree', 'set'], same: ['commit to', 'adopt', 'agree on'], longer: ['commit themselves to', 'agree to adopt', 'undertake to establish'],
         plain: ['agree on', 'settle on', 'sign up to'], formal: ['undertake to adopt', 'commit themselves to', 'resolve to establish'] },
    2: { shorter: ['establish', 'implement', 'enact'], same: ['establish without delay', 'put in place', 'implement'], longer: ['establish and implement without delay', 'fully put in place', 'fully implement'],
         plain: ['set up now', 'put in place now', 'make'], formal: ['establish forthwith', 'implement in full', 'give full effect to'] },
  } },
};
// strength is shown relative to the wording the rail opened on
const STRENGTH_WORDS = { '-3': 'weakest', '-2': 'weaker', '-1': 'weak', 0: 'same', 1: 'strong', 2: 'stronger', 3: 'strongest' };
const strengthWord = r => STRENGTH_WORDS[Math.max(-3, Math.min(3, r.level - r.base))];

/* ---------------- the statement ---------------- */
const START = () => ({
  title: 'Joint statement · Forum on Cooperation at Sea (an invented example)',
  sentences: [
    { id: 's1', lead: 'Progress', text: 'We note the progress made since our last meeting in improving the safety of navigation in shared waters.', state: 'draft', version: 1, targets: [{ id: 'note', start: 3, end: 7, level: 0 }] },
    { id: 's2', lead: 'Cooperation', text: 'Members will work towards a common approach to search and rescue, consistent with international law.', state: 'draft', version: 1, targets: [{ id: 'work', start: 13, end: 25, level: 0 }] },
    { id: 's3', text: 'We [encourage / urge] all parties to share information on incidents at sea in a timely manner.', state: 'draft', version: 1, targets: [] },
    { id: 's4', lead: 'Review', text: 'The Forum should review these arrangements every two years.', state: 'agreed', version: 3, targets: [] },
    { id: 's5', text: 'Nothing in this statement creates new legal obligations.', state: 'agreed', version: 2, targets: [] },
  ],
});

/* ---------------- state ---------------- */
const S = { doc: START(), focus: 's1', mode: 'rest', rail: null, brk: null, changed: null, undo: [] };
const sent = id => S.doc.sentences.find(s => s.id === id);
const BRACKET = /\[([^\[\]]*)\]/g, SEP = ' / ';
function bracketsIn(text) {
  const out = []; let m; BRACKET.lastIndex = 0;
  while ((m = BRACKET.exec(text))) {
    const start = m.index, alts = []; let pos = start + 1;
    m[1].split(SEP).forEach(a => { alts.push({ text: a, start: pos, end: pos + a.length }); pos += a.length + SEP.length; });
    out.push({ start, end: start + m[0].length, alts });
  }
  return out;
}

/* ---------------- the record ---------------- */
const logEl = $('#log');
let t0 = Date.now();
function record(kind, detail) {
  const li = document.createElement('li');
  const secs = Math.round((Date.now() - t0) / 1000);
  li.innerHTML = `${String(Math.floor(secs / 60)).padStart(2, '0')}:${String(secs % 60).padStart(2, '0')} <b>${esc(kind)}</b> ${esc(detail || '')}`;
  logEl.appendChild(li); logEl.scrollTop = logEl.scrollHeight;
}

/* ---------------- proposals at the current dials ---------------- */
function options(r) {
  const tree = TREE[r.tid];
  const level = tree.levels[String(r.level)];
  const list = r.register === 'institutional' ? level[r.length] : level[r.register];
  return { opts: list.map(t => ({ t, flags: [] })) };
}
function markChanges(src, out) {
  const known = new Set((src.toLowerCase().match(/[\w']+/g) || []));
  return esc(out).split(/(\s+)/).map(w => { const k = w.toLowerCase().replace(/[^\w']/g, ''); return k && !known.has(k) ? `<span class="chg">${w}</span>` : w; }).join('');
}

/* ---------------- rendering ---------------- */
const stage = $('#stage');
function decorate(s) {
  const txt = s.text, cls = Array.from({ length: txt.length }, () => []), attr = Array.from({ length: txt.length }, () => '');
  bracketsIn(txt).forEach(b => {
    for (let i = b.start; i < b.end; i++) { cls[i].push('bk'); attr[i] = `data-b="${b.start}"`; }
    b.alts.forEach((a, k) => { const cur = S.mode === 'bracket' && S.brk && S.brk.sid === s.id && S.brk.start === b.start && k === S.brk.cur;
      for (let i = a.start; i < a.end; i++) { cls[i] = cls[i].filter(c => c !== 'bk'); cls[i].push('alt'); if (cur) cls[i].push('altcur'); } });
  });
  s.targets.forEach(t => { if (t.start < 0) return; for (let i = t.start; i < t.end; i++) { cls[i].push('tw'); attr[i] = `data-t="${t.id}"`; } });
  if (S.mode === 'rail' && S.rail.sid === s.id) { const t = target(S.rail); for (let i = t.start; i < t.end; i++) cls[i].push('sel'); }
  if (S.changed && S.changed.sid === s.id) for (let i = S.changed.start; i < S.changed.end; i++) cls[i].push('new');
  let out = '', run = '', key = null;
  for (let i = 0; i <= txt.length; i++) {
    const k = i < txt.length ? cls[i].join(' ') + '|' + attr[i] : null;
    if (k !== key) { if (run) { const [c, a] = key.split('|'); out += c || a ? `<span class="${c}" ${a}>${esc(run)}</span>` : esc(run); } run = ''; key = k; }
    if (i < txt.length) run += txt[i];
  }
  return out;
}
function target(r) { return sent(r.sid).targets.find(t => t.id === r.tid); }
function render() {
  const rows = S.doc.sentences.map((s, i) => {
    const nb = bracketsIn(s.text).length;
    const mk = (s.state === 'agreed' ? '<span class="mk agreed">Agreed</span>' : s.version > 1 ? `<span class="mk v">v${s.version}</span>` : '') + (nb ? `<span class="mk brk">${nb} bracket${nb > 1 ? 's' : ''}</span>` : '');
    return `<div class="row ${s.state}${s.id === S.focus ? ' focus' : ''}" data-id="${s.id}">
      <div class="gut"><span class="num">${i + 1}</span>${mk}</div>
      <div>${s.lead ? `<div class="lead">${esc(s.lead)}</div>` : ''}<p class="sent">${decorate(s)}</p>${panel(s)}</div></div>`;
  }).join('');
  stage.innerHTML = `<div class="stmt-title">${esc(S.doc.title)}</div>${rows}`;
  const n = S.doc.sentences.length, a = S.doc.sentences.filter(s => s.state === 'agreed').length;
  const b = S.doc.sentences.reduce((k, s) => k + bracketsIn(s.text).length, 0);
  $('#readout').textContent = a === n ? `All ${n} agreed` : `${a} of ${n} agreed${b ? ` · ${b} in brackets` : ''}`;
  $('#progress').style.width = `${100 * a / n}%`;
  $('#hintline').textContent = S.mode === 'rail' ? '←→ strength · ↑↓ length · R register · ⇥ next · ↵ accept · ⇧↵ keep as alternative · esc'
    : S.mode === 'bracket' ? '↑↓ choose · ↵ settle on this wording · esc' : 'Double-click an underlined word · click a sentence, ⇧↵ agree · undo';
  stage.querySelectorAll('.cell').forEach(c => c.addEventListener('click', () => { S.rail.cur = +c.dataset.i; accept(); }));
  stage.querySelectorAll('.slot').forEach(c => c.addEventListener('click', () => { S.brk.cur = +c.dataset.i; settle(); }));
  if (typeof placeSpot === 'function') requestAnimationFrame(placeSpot);
}
function panel(s) {
  if (S.mode === 'rail' && S.rail.sid === s.id) {
    const r = S.rail, tree = TREE[r.tid], { opts } = options(r);
    const strength = `<span class="v">${strengthWord(r)}</span>`;
    const cells = opts.map((o, i) => `<button type="button" class="cell${i === r.cur ? ' cur' : ''}" data-i="${i}"><span class="n">${i + 1}</span><p>${markChanges(r.source, o.t)}<span class="src">local</span></p></button>`).join('');
    return `<div class="panel"><div class="dials"><span><span class="lab">Strength ←→</span> ${strength}</span><span><span class="lab">Length ↑↓</span> <span class="v">${r.length}</span></span><span><span class="lab">Register R</span> <span class="v">${r.register === 'formal' ? 'formal diplomatic' : r.register}</span></span></div><div class="grid">${cells}</div></div>`;
  }
  if (S.mode === 'bracket' && S.brk.sid === s.id) {
    const b = S.brk;
    return `<div class="panel brkp"><div class="dials"><span class="lab" style="color:var(--brk)">In brackets</span><span>${b.alts.length} alternatives · settle on one when the room agrees</span></div>${b.alts.map((a, i) => `<button type="button" class="slot${i === b.cur ? ' cur' : ''}" data-i="${i}"><p>${esc(a)}</p><span class="k">${i === b.cur ? '↵ settle' : ''}</span></button>`).join('')}</div>`;
  }
  return '';
}

/* ---------------- actions ---------------- */
let toastT;
function toast(msg, ok) { const t = $('#toast'); t.textContent = msg; t.className = 'toast' + (ok ? ' ok' : ''); clearTimeout(toastT); toastT = setTimeout(() => { t.textContent = ''; }, 5000); }
function snapshot() { S.undo.push(JSON.stringify(S.doc)); if (S.undo.length > 50) S.undo.shift(); }
function openRail(sid, tid) {
  const s = sent(sid), t = s.targets.find(x => x.id === tid);
  S.focus = sid; S.mode = 'rail'; S.changed = null;
  S.rail = { sid, tid, level: t.level, base: t.level, length: 'same', register: 'institutional', cur: 0, source: s.text.slice(t.start, t.end) };
  record('rail.open', `“${S.rail.source}”`); record('proposal.local', '3 shown');
  render(); emit({ type: 'open', tid });
}
function dial(kind, delta) {
  const r = S.rail, tree = TREE[r.tid];
  if (kind === 'strength') {
    const min = tree.min, max = tree.max;
    const next = Math.max(min, Math.min(max, r.level + delta));
    if (next === r.level) { toast(delta > 0 ? 'That is the strongest wording here' : 'That is the weakest wording here'); return; }
    r.level = next;
  } else if (kind === 'length') {
    const L = ['shorter', 'same', 'longer'], i = L.indexOf(r.length) + delta;
    if (i < 0 || i > 2) { toast(delta > 0 ? 'Already the longest' : 'Already the shortest'); return; }
    r.length = L[i];
  } else {
    const R = ['plain', 'institutional', 'formal']; r.register = R[(R.indexOf(r.register) + 1) % 3];
  }
  r.cur = 0; record('proposal.local', `3 shown · ${strengthWord(r)} · ${r.length} · ${r.register}`);
  render(); emit({ type: 'dial', kind, level: r.level, length: r.length, register: r.register });
}
function closeRail(logIt = true) {
  if (S.mode === 'rail' && logIt) record('reject', '3 proposals not chosen');
  S.mode = 'rest'; S.rail = null; S.brk = null; render();
}
function edit(s, start, end, text) {
  const delta = text.length - (end - start);
  s.text = s.text.slice(0, start) + text + s.text.slice(end);
  s.targets.forEach(t => { if (t.start >= end) { t.start += delta; t.end += delta; } });
  s.version += 1; if (s.state === 'agreed') s.state = 'draft';
}
function accept() {
  const r = S.rail, s = sent(r.sid), t = target(r), o = options(r).opts[r.cur];
  snapshot();
  edit(s, t.start, t.end, o.t); t.end = t.start + o.t.length; t.level = r.level;
  S.changed = { sid: s.id, start: t.start, end: t.end };
  record('accept', `local · “${r.source}” → “${o.t}”`);
  S.mode = 'rest'; S.rail = null; render(); toast(`Accepted “${o.t}” · sentence ${s.id.slice(1)} is now v${s.version}`, true);
  emit({ type: 'accept', tid: t.id });
}
function keepAlternative() {
  const r = S.rail, s = sent(r.sid), t = target(r), o = options(r).opts[r.cur];
  snapshot();
  const inner = `[${r.source}${SEP}${o.t}]`, start = t.start, end = t.end;
  edit(s, start, end, inner); t.start = -1; t.end = -1;   // the word is in brackets now: the room settles it
  record('accept.alternative', `“${r.source}” kept beside “${o.t}”`); record('bracket.open', `[${r.source} / ${o.t}]`);
  S.mode = 'rest'; S.rail = null; render(); toast('Kept as an alternative: the room now settles the bracket', true);
  emit({ type: 'bracket-open' });
}
function openBracket(sid, start) {
  const s = sent(sid), b = bracketsIn(s.text).find(x => x.start === start); if (!b) return;
  S.focus = sid; S.mode = 'bracket'; S.rail = null; S.changed = null;
  S.brk = { sid, start: b.start, end: b.end, alts: b.alts.map(a => a.text), cur: 0 };
  render(); emit({ type: 'bracket' });
}
function settle() {
  const b = S.brk, s = sent(b.sid), chosen = b.alts[b.cur];
  snapshot();
  edit(s, b.start, b.end, chosen);
  // a bracket made from a demo word becomes that word again, so it can be reopened
  const back = s.targets.find(t => t.start < 0);
  if (back) { back.start = b.start; back.end = b.start + chosen.length; }
  S.changed = { sid: s.id, start: b.start, end: b.start + chosen.length };
  record('bracket.settle', `“${chosen}” (from ${b.alts.map(a => `“${a}”`).join(', ')})`);
  S.mode = 'rest'; S.brk = null; render(); toast(`Settled on “${chosen}”`, true);
  emit({ type: 'settle', sid: s.id });
}
function toggleAgreed(sid) {
  const s = sent(sid);
  if (s.state !== 'agreed' && bracketsIn(s.text).length) {
    toast('Settle the brackets in this sentence before agreeing it'); record('blocked', `sentence ${sid.slice(1)} has an open bracket`);
    emit({ type: 'blocked', sid }); return;
  }
  snapshot(); s.state = s.state === 'agreed' ? 'draft' : 'agreed';
  record('state', `sentence ${sid.slice(1)} → ${s.state}`); render();
  const all = S.doc.sentences.every(x => x.state === 'agreed');
  if (all) toast('All agreed: nothing is agreed until everything is agreed, and now everything is', true);
  emit({ type: s.state === 'agreed' ? 'agree' : 'unagree', sid, all });
}
function undo() {
  if (!S.undo.length) { toast('Nothing to undo'); return; }
  S.doc = JSON.parse(S.undo.pop()); S.mode = 'rest'; S.rail = null; S.brk = null; S.changed = null;
  record('undo', ''); render();
}

/* ---------------- input ---------------- */
function key(k, shift) {
  if (S.mode === 'rail') {
    const n = options(S.rail).opts.length;
    if (k === 'ArrowRight') return dial('strength', 1);
    if (k === 'ArrowLeft') return dial('strength', -1);
    if (k === 'ArrowUp') return dial('length', 1);
    if (k === 'ArrowDown') return dial('length', -1);
    if (k === 'r' || k === 'R') return dial('register');
    if (k === 'Tab') { S.rail.cur = (S.rail.cur + (shift ? -1 : 1) + n) % n; render(); return; }
    if (/^[1-3]$/.test(k)) { S.rail.cur = +k - 1; render(); return; }
    if (k === 'Enter' && shift) return keepAlternative();
    if (k === 'Enter') return accept();
    if (k === 'Escape') return closeRail();
    if (k === 'Undo') { closeRail(false); return undo(); }
    return;
  }
  if (S.mode === 'bracket') {
    const n = S.brk.alts.length;
    if (k === 'ArrowDown' || k === 'ArrowRight' || k === 'Tab') { S.brk.cur = (S.brk.cur + 1) % n; render(); return; }
    if (k === 'ArrowUp' || k === 'ArrowLeft') { S.brk.cur = (S.brk.cur - 1 + n) % n; render(); return; }
    if (k === 'Enter') return settle();
    if (k === 'Escape') return closeRail(false);
    return;
  }
  if (k === 'Enter' && shift) return toggleAgreed(S.focus);
  if (k === 'Undo') return undo();
  if (k === 'ArrowDown' || k === 'ArrowUp') {
    const i = S.doc.sentences.findIndex(s => s.id === S.focus) + (k === 'ArrowDown' ? 1 : -1);
    if (S.doc.sentences[i]) { S.focus = S.doc.sentences[i].id; render(); }
    return;
  }
  if (['ArrowLeft', 'ArrowRight', 'r', 'R', 'Enter', 'Tab'].includes(k)) toast('Double-click an underlined word first');
}
stage.addEventListener('keydown', e => {
  const mod = e.metaKey || e.ctrlKey;
  if (mod && e.key.toLowerCase() === 'z') { e.preventDefault(); return key('Undo'); }
  if (mod || e.altKey) return;
  const handled = ['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Enter', 'Escape', 'Tab', 'r', 'R', '1', '2', '3'];
  if (!handled.includes(e.key)) return;
  if (e.key === 'Tab' && S.mode !== 'rail' && S.mode !== 'bracket') return;   // let Tab leave the demo when nothing is open
  e.preventDefault(); key(e.key, e.shiftKey);
});
document.querySelectorAll('#keys .key').forEach(b => b.addEventListener('click', () => {
  const k = b.dataset.key; stage.focus({ preventScroll: true });
  if (k === 'ShiftEnter') key('Enter', true); else key(k, false);
}));
function hit(e) {
  const t = e.target.closest('[data-t]'), b = e.target.closest('[data-b]'), row = e.target.closest('.row');
  return { t, b, row };
}
stage.addEventListener('dblclick', e => {
  const { t, b, row } = hit(e); getSelection && getSelection().removeAllRanges();
  if (b) return openBracket(row.dataset.id, +b.dataset.b);
  if (t) return openRail(row.dataset.id, t.dataset.t);
  if (row && e.target.closest('.sent')) toast('In this demo, proposals are written in advance for the underlined words. In the app, any word or phrase works.');
});
stage.addEventListener('click', e => {
  if (e.target.closest('.panel')) return;
  const { t, b, row } = hit(e);
  if (!row) return;
  if (S.focus !== row.dataset.id) { if (S.mode !== 'rest') closeRail(); S.focus = row.dataset.id; render(); }
  // a touch screen has no double-click: a tap on an underlined word or a bracket opens it
  if (e.pointerType === 'touch' || (e.detail === 1 && matchMedia('(hover: none)').matches)) {
    if (b) openBracket(row.dataset.id, +b.dataset.b); else if (t) openRail(row.dataset.id, t.dataset.t);
  }
});

/* ---------------- the guided tour ---------------- */
const kbd = s => `<kbd>${s}</kbd>`;
const STEPS = [
  { title: 'Open proposals', body: `<p>Double-click <strong>note</strong> in sentence 1. (On a touch screen, tap it.)</p>`,
    done: e => e.type === 'open' && e.tid === 'note' },
  { title: 'Make it stronger', body: `<p>Press ${kbd('→')} for stronger wording.</p>`,
    done: e => e.type === 'dial' && e.kind === 'strength' },
  { title: 'Stronger still', body: `<p>Press ${kbd('→')} again for <strong>stronger</strong>. ${kbd('←')} goes back towards weak.</p>`,
    done: e => e.type === 'dial' && S.rail && S.rail.tid === 'note' && S.rail.level - S.rail.base === 2 },
  { title: 'Longer, shorter, plainer', body: `<p>${kbd('↑')} longer, ${kbd('↓')} shorter, ${kbd('R')} changes the register.</p>`,
    done: e => e.type === 'dial' && (e.kind === 'length' || e.kind === 'register') },
  { title: 'Choose one', body: `<p>${kbd('⇥')} moves between proposals; ${kbd('↵')} accepts one.</p>`,
    done: e => e.type === 'accept' || e.type === 'bracket-open' },
  { title: 'Open brackets', body: `<p>Click sentence 3 and press ${kbd('⇧↵')} to agree it.</p>`,
    done: e => e.type === 'blocked' || (e.type === 'agree' && e.sid === 's3') },
  { title: 'Settle the bracket', body: `<p>Double-click the bracket, pick with ${kbd('↑')} ${kbd('↓')}, press ${kbd('↵')}.</p>`,
    done: e => e.type === 'settle' && e.sid === 's3' },
  { title: 'Agree it', body: `<p>Press ${kbd('⇧↵')} to agree sentence 3.</p>`,
    done: e => e.type === 'agree' && e.sid === 's3' },
  { title: 'Any phrase', body: `<p>Double-click <strong>work towards</strong> in sentence 2.</p>`,
    done: e => e.type === 'open' && e.tid === 'work' },
  { title: 'Finish', body: `<p>Accept a proposal, then agree sentences 1 and 2.</p>`,
    done: e => e.type === 'agree' && e.all, final: true },
];
// what each step's spotlight falls on, in order; a function, because the page changes as the visitor works
const SPOT = [
  () => '.row[data-id="s1"]',
  () => '.row[data-id="s1"]', () => '.row[data-id="s1"]', () => '.row[data-id="s1"]', () => '.row[data-id="s1"]',
  () => '.row[data-id="s3"]', () => '.row[data-id="s3"]', () => '.row[data-id="s3"]',
  () => '.row[data-id="s2"]',
  () => '.row:not(.agreed)',
];
const screenEl = $('#screen');
const spot = document.createElement('div'); spot.className = 'spot'; spot.setAttribute('aria-hidden', 'true'); screenEl.appendChild(spot);
function placeSpot() {
  const sel = finished ? null : SPOT[step] && SPOT[step]();
  const els = sel ? [...screenEl.querySelectorAll(sel)] : [];
  if (!els.length) { spot.classList.remove('on'); return; }
  // one box around everything the step involves
  const rs = els.map(e => e.getBoundingClientRect());
  const L = Math.min(...rs.map(q => q.left)), T = Math.min(...rs.map(q => q.top));
  const r = { left: L, top: T, width: Math.max(...rs.map(q => q.right)) - L, height: Math.max(...rs.map(q => q.bottom)) - T };
  const a = screenEl.getBoundingClientRect(), pad = 10;
  Object.assign(spot.style, { left: `${r.left - a.left - pad}px`, top: `${r.top - a.top - pad}px`, width: `${r.width + 2 * pad}px`, height: `${r.height + 2 * pad}px` });
  spot.classList.add('on');
}
addEventListener('resize', placeSpot);
let step = 0, finished = false;
function showStep() {
  const s = STEPS[step];
  $('#gcount').textContent = finished ? 'Done' : `Step ${step + 1} of ${STEPS.length}`;
  $('#gtitle').textContent = finished ? 'The statement is agreed' : s.title;
  $('#gbody').innerHTML = finished
    ? `<p>People chose every word. <a href="#download">Download [bracket]</a></p>`
    : s.body;
  $('#gback').disabled = step === 0 && !finished;
  $('#gnext').hidden = finished || s.final;
  requestAnimationFrame(placeSpot);
}
function emit(e) {
  if (finished) return;
  const s = STEPS[step];
  if (!s.done(e)) return;
  if (s.final) finished = true; else step += 1;
  showStep();
}
$('#gnext').addEventListener('click', () => { if (step < STEPS.length - 1) { step++; showStep(); } });
$('#gback').addEventListener('click', () => { if (finished) { finished = false; } else if (step > 0) step--; showStep(); });
record('session.begin', '5 sentences');
render(); showStep();

})();
