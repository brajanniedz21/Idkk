import { createClient } from '/vendor/supabase.js';

/* ================= utilities ================= */
const $ = s => document.querySelector(s);
const clamp = (x, a, b) => Math.min(b, Math.max(a, x));
function mulberry32(a){return function(){a|=0;a=a+0x6D2B79F5|0;let t=Math.imul(a^a>>>15,1|a);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296}}
function hash(s){let h=1779033703;for(let i=0;i<s.length;i++){h=Math.imul(h^s.charCodeAt(i),3432918353);h=h<<13|h>>>19}return h>>>0}
const MINUS = '−';
const N = x => Number(x) || 0;
const fmtP = x => '£' + N(x).toFixed(2);
const fmtK = x => { x = N(x); return x >= 1e6 ? '£' + (x/1e6).toFixed(2) + 'm' : x >= 1e3 ? '£' + (x/1e3).toFixed(1) + 'k' : '£' + Math.round(x); };
const fmtPct = x => (x >= 0 ? '+' : MINUS) + Math.abs(x).toFixed(2) + '%';
const fmtVol = x => { x = N(x); return x >= 1e6 ? (x/1e6).toFixed(1) + 'm' : x >= 1e3 ? (x/1e3).toFixed(1) + 'k' : String(Math.round(x)); };
const cls = x => x > 1e-9 ? 'up' : x < -1e-9 ? 'down' : 'flat';
const arrow = x => x > 1e-9 ? '▲' : x < -1e-9 ? '▼' : '·';
const pad = n => String(n).padStart(2, '0');
const ts = d => { d = d ? new Date(d) : new Date(); return pad(d.getHours()) + ':' + pad(d.getMinutes()) + ':' + pad(d.getSeconds()); };
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const chipPct = x => '<span class="' + cls(x) + '">' + arrow(x) + ' ' + fmtPct(x * 100) + '</span>';
const SECTORS = { FIT:'Fitness', BIZ:'Business', COD:'Coding', ART:'Art', EDU:'Education', CRE:'Content Creation' };

const MARKET_TZ = 'Europe/London'; // must match the MARKET_TZ env var on Netlify
function marketHour(){ return Number(new Intl.DateTimeFormat('en-GB',{timeZone:MARKET_TZ,hour:'2-digit',hour12:false}).format(new Date())) % 24; }
const marketOpen = () => marketHour() >= 8;
function marketDayStr(d){ const f=new Intl.DateTimeFormat('en-CA',{timeZone:MARKET_TZ,year:'numeric',month:'2-digit',day:'2-digit'}); return f.format(d||new Date()); }

/* ================= state ================= */
let sb = null, session = null;
const S = {
  listings: [], byT: {}, byId: {},
  holders: {},              // listing_id -> {holders, held}
  candles: {},              // listing_id -> [{day,o,h,l,c,v}] asc
  events: [], lastEventId: 0,
  account: null, myListing: null,
  holdings: {},             // listing_id -> {shares, cost}
  trades: [], dividends: [], stakes: [],
  follows: new Set(),
  guidanceOpen: {},         // listing_id -> guidance row
  myActionsToday: 0,
  view: 'auth', sel: null,
};

const dayChg = u => (N(u.price) - N(u.prev_close)) / N(u.prev_close);
const mcap = u => N(u.price) * N(u.shares);
function weekRef(u){ const c = S.candles[u.id]; return c && c.length >= 5 ? N(c[c.length-5].c) : N(u.prev_close); }
const weekChg = u => (N(u.price) - weekRef(u)) / weekRef(u);

async function api(path, body){
  const r = await fetch('/api/' + path, {
    method: 'POST',
    headers: { 'content-type': 'application/json', authorization: 'Bearer ' + session.access_token },
    body: JSON.stringify(body || {}),
  });
  let d; try { d = await r.json(); } catch { d = { error: 'The exchange did not answer. Try again.' }; }
  return d;
}

/* ================= auth & routing ================= */
function showOnly(id){
  document.querySelectorAll('.view').forEach(el => el.classList.remove('on'));
  $('#view-' + id).classList.add('on');
}
async function route(){
  if (!session){
    $('#nav').hidden = true; $('#tape').hidden = true; $('#signout').hidden = true;
    $('#cash').textContent = '';
    showOnly('auth');
    return;
  }
  $('#signout').hidden = false;
  const { data: mine } = await sb.from('listings').select('*').eq('user_id', session.user.id).maybeSingle();
  if (!mine){ showOnly('onboard'); return; }
  S.myListing = mine;
  $('#nav-me').textContent = mine.ticker;
  await enterApp();
}

async function boot(){
  if (!window.MX_CONFIG?.SUPABASE_URL){
    showOnly('auth');
    $('#auth-msg').textContent = 'Not configured: config.js is missing. See SETUP.md.';
    return;
  }
  sb = createClient(window.MX_CONFIG.SUPABASE_URL, window.MX_CONFIG.SUPABASE_ANON_KEY);
  const { data } = await sb.auth.getSession();
  session = data.session;
  sb.auth.onAuthStateChange((_e, s) => { session = s; });
  await route();
}

$('#auth-form').addEventListener('submit', async e => {
  e.preventDefault();
  $('#auth-msg').textContent = 'Signing in…';
  const { data, error } = await sb.auth.signInWithPassword({
    email: $('#auth-email').value.trim(), password: $('#auth-pass').value,
  });
  if (error){ $('#auth-msg').textContent = error.message; return; }
  session = data.session; $('#auth-msg').textContent = '';
  await route();
});
$('#btn-signup').addEventListener('click', async () => {
  const email = $('#auth-email').value.trim(), password = $('#auth-pass').value;
  if (!email || password.length < 8){ $('#auth-msg').textContent = 'Enter an email and a password of at least 8 characters.'; return; }
  $('#auth-msg').textContent = 'Creating account…';
  const { data, error } = await sb.auth.signUp({ email, password });
  if (error){ $('#auth-msg').textContent = error.message; return; }
  if (data.session){ session = data.session; await route(); }
  else $('#auth-msg').textContent = 'Confirmation email sent. Verify your address, then sign in.';
});
$('#signout').addEventListener('click', async () => { await sb.auth.signOut(); session = null; location.hash=''; await route(); });

$('#ipo-form').addEventListener('submit', async e => {
  e.preventDefault();
  $('#ipo-msg').textContent = 'Filing prospectus…';
  const res = await api('ipo', {
    display_name: $('#ipo-name').value, ticker: $('#ipo-ticker').value.toUpperCase(),
    company: $('#ipo-company').value, sector: $('#ipo-sector').value,
    pitch: $('#ipo-pitch').value, outlook: $('#ipo-outlook').value,
    risks: [$('#ipo-risk1').value, $('#ipo-risk2').value].filter(Boolean),
  });
  if (res.error){ $('#ipo-msg').textContent = res.error; return; }
  $('#ipo-msg').textContent = '';
  await route();
});

/* ================= data loading ================= */
function indexListings(rows){
  S.listings = rows;
  S.byT = {}; S.byId = {};
  rows.forEach(u => { S.byT[u.ticker] = u; S.byId[u.id] = u; });
  if (S.myListing) S.myListing = S.byT[S.myListing.ticker] || S.myListing;
}

async function loadCore(){
  const from30 = new Date(Date.now() - 33 * 864e5).toISOString().slice(0, 10);
  const [ls, hc, cd, ev, acct, hold, fol, gd] = await Promise.all([
    sb.from('listings').select('*'),
    sb.from('holder_counts').select('*'),
    sb.from('candles_d').select('*').gte('day', from30).order('day', { ascending: true }),
    sb.from('events').select('*').order('id', { ascending: false }).limit(50),
    sb.from('accounts').select('*').eq('user_id', session.user.id).maybeSingle(),
    sb.from('holdings').select('*').eq('user_id', session.user.id),
    sb.from('follows').select('listing_id').eq('follower', session.user.id),
    sb.from('guidance').select('*').eq('status', 'open'),
  ]);
  indexListings(ls.data || []);
  S.holders = Object.fromEntries((hc.data || []).map(r => [r.listing_id, r]));
  S.candles = {};
  (cd.data || []).forEach(r => { (S.candles[r.listing_id] = S.candles[r.listing_id] || []).push(r); });
  S.events = ev.data || [];
  S.lastEventId = S.events[0]?.id || 0;
  S.account = acct.data;
  S.holdings = Object.fromEntries((hold.data || []).map(h => [h.listing_id, h]));
  S.follows = new Set((fol.data || []).map(f => f.listing_id));
  S.guidanceOpen = Object.fromEntries((gd.data || []).map(g => [g.listing_id, g]));
  if (S.myListing){
    const { count } = await sb.from('actions').select('*', { count: 'exact', head: true })
      .eq('listing_id', S.myListing.id).eq('day', marketDayStr()).eq('kind', 'session');
    S.myActionsToday = count || 0;
  }
}

async function refreshLite(){
  if (!session || !S.myListing) return;
  const [ls, ev, acct, hold] = await Promise.all([
    sb.from('listings').select('*'),
    sb.from('events').select('*').gt('id', S.lastEventId).order('id', { ascending: true }),
    sb.from('accounts').select('*').eq('user_id', session.user.id).maybeSingle(),
    sb.from('holdings').select('*').eq('user_id', session.user.id),
  ]);
  if (ls.data?.length) indexListings(ls.data);
  S.account = acct.data || S.account;
  S.holdings = Object.fromEntries((hold.data || []).map(h => [h.listing_id, h]));
  (ev.data || []).forEach(pushEvent);
  renderLive();
}

function pushEvent(row){
  if (row.id <= S.lastEventId) return;
  S.lastEventId = row.id;
  S.events.unshift(row); S.events = S.events.slice(0, 80);
  const el = $('#feed');
  if (el){ el.insertAdjacentHTML('afterbegin', feedHTML(row)); while (el.children.length > 80) el.lastChild.remove(); }
  if (row.kind === 'bell') showBell(row.body);
}
function feedHTML(it){
  const mv = it.move == null ? '' : `<span class="mv ${cls(N(it.move))}">${arrow(N(it.move))} ${fmtPct(N(it.move) * 100)}</span>`;
  const tk = it.ticker ? `<span class="tk ${it.move == null ? 'dim' : cls(N(it.move))}" data-go="${esc(it.ticker)}">${esc(it.ticker)}</span>` : '';
  const sys = it.kind !== 'wire';
  return `<div class="fi${sys ? ' sys' : ''}"><span class="ts">${ts(it.ts)}</span>${tk}<span class="tx">${esc(it.body)}</span>${mv}</div>`;
}

let bellTimer = null;
function showBell(txt){
  const b = $('#bell'); b.textContent = txt; b.classList.add('show');
  clearTimeout(bellTimer); bellTimer = setTimeout(() => b.classList.remove('show'), 6000);
}

/* ================= composite & sectors ================= */
function composite(){
  let v = 0, p = 0;
  S.listings.forEach(u => { v += mcap(u); p += N(u.prev_close) * N(u.shares); });
  return { v: v / 1000, chg: p ? (v - p) / p : 0 };
}
function sectorStats(code){
  const list = S.listings.filter(u => u.sector === code);
  let v = 0, p = 0, w = 0;
  list.forEach(u => { v += mcap(u); p += N(u.prev_close) * N(u.shares); w += weekRef(u) * N(u.shares); });
  return { v, chg: p ? (v - p) / p : 0, wk: w ? (v - w) / w : 0, list };
}

/* ================= charts ================= */
const CSSC = getComputedStyle(document.documentElement);
const C_UP = '#3fce7c', C_DOWN = '#e5484d',
      C_MUTED = CSSC.getPropertyValue('--muted').trim(), C_FAINT = CSSC.getPropertyValue('--faint').trim(),
      C_LINE = CSSC.getPropertyValue('--line').trim(), C_AMBER = CSSC.getPropertyValue('--amber').trim();

const tickCache = {}; // listing_id -> {at, bars}
async function intradayBars(u){
  const c = tickCache[u.id];
  if (c && Date.now() - c.at < 30e3) return c.bars;
  const since = new Date(Date.now() - 18 * 3600e3).toISOString();
  const { data } = await sb.from('ticks').select('ts, price, vol')
    .eq('listing_id', u.id).gte('ts', since).order('ts', { ascending: true }).limit(1000);
  const bars = [];
  (data || []).forEach(t => {
    const bucket = Math.floor(new Date(t.ts).getTime() / 3e5) * 3e5;
    const px = N(t.price), b = bars[bars.length - 1];
    if (b && b.t === bucket){ b.c = px; b.h = Math.max(b.h, px); b.l = Math.min(b.l, px); b.v += N(t.vol); }
    else bars.push({ t: bucket, o: b ? b.c : px, h: px, l: px, c: px, v: N(t.vol) });
  });
  tickCache[u.id] = { at: Date.now(), bars };
  return bars;
}
function dailyBars(u, n){
  const hist = (S.candles[u.id] || []).map(r => ({ day: r.day, o: N(r.o), h: N(r.h), l: N(r.l), c: N(r.c), v: N(r.v) }));
  const today = { day: marketDayStr(), o: N(u.day_open), h: N(u.day_high), l: N(u.day_low), c: N(u.price), v: N(u.day_vol) };
  const all = hist.concat([today]);
  return n ? all.slice(-n) : all;
}
function barLabel(b){
  if (b.t){ const d = new Date(b.t); return pad(d.getHours()) + ':' + pad(d.getMinutes()); }
  const d = new Date(b.day + 'T12:00:00');
  return d.getDate() + ' ' + ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][d.getMonth()];
}

function chartify(canvas, ohlcEl, getUser){
  const st = { range: '1D', hover: -1, bars: [] };
  async function load(){
    const u = getUser(); if (!u) return;
    if (st.range === '1D'){
      st.bars = await intradayBars(u);
      if (!st.bars.length) st.bars = dailyBars(u, 1);
    } else st.bars = dailyBars(u, st.range === '1M' ? 22 : st.range === '3M' ? 65 : 0);
    paint();
  }
  function paint(){
    const u = getUser(); if (!u) return;
    const dpr = window.devicePixelRatio || 1;
    const W = canvas.clientWidth, H = canvas.clientHeight;
    if (!W || !H) return;
    if (canvas.width !== W * dpr){ canvas.width = W * dpr; canvas.height = H * dpr; }
    const x = canvas.getContext('2d'); x.setTransform(dpr, 0, 0, dpr, 0, 0); x.clearRect(0, 0, W, H);
    const bars = st.bars, n = bars.length; if (!n) return;
    const padL = 6, padR = 58, padT = 8, xH = 16, volH = Math.round(H * 0.16), gap = 6;
    const priceH = H - padT - xH - volH - gap, plotW = W - padL - padR;
    let hi = -1e9, lo = 1e9, vMax = 1;
    bars.forEach(b => { hi = Math.max(hi, b.h); lo = Math.min(lo, b.l); vMax = Math.max(vMax, b.v || 0); });
    const span = (hi - lo) || 1; hi += span * 0.05; lo -= span * 0.05;
    const Y = p => padT + (hi - p) / (hi - lo) * priceH;
    const X = i => padL + (i + 0.5) / n * plotW;
    const bw = Math.max(1.5, Math.min(11, plotW / n * 0.62));
    x.font = '10px ' + getComputedStyle(document.body).fontFamily;
    x.textAlign = 'left'; x.textBaseline = 'middle';
    for (let g = 0; g <= 4; g++){
      const p = lo + (hi - lo) * g / 4, y = Y(p);
      x.strokeStyle = C_LINE; x.globalAlpha = 0.5; x.beginPath(); x.moveTo(padL, y + .5); x.lineTo(W - padR, y + .5); x.stroke(); x.globalAlpha = 1;
      x.fillStyle = C_FAINT; x.fillText(p.toFixed(2), W - padR + 8, y);
    }
    if (st.range === '1D'){
      const y = Y(N(u.prev_close));
      if (y > padT && y < padT + priceH){
        x.strokeStyle = C_FAINT; x.setLineDash([2, 3]); x.beginPath(); x.moveTo(padL, y + .5); x.lineTo(W - padR, y + .5); x.stroke(); x.setLineDash([]);
      }
    }
    bars.forEach((b, i) => {
      const up = b.c >= b.o, col = up ? C_UP : C_DOWN, cx = X(i);
      if (b.v){ x.globalAlpha = 0.45; x.fillStyle = col; const vh = (b.v / vMax) * volH; x.fillRect(cx - bw/2, H - xH - vh, bw, vh); x.globalAlpha = 1; }
      x.strokeStyle = col; x.beginPath(); x.moveTo(cx + .5, Y(b.h)); x.lineTo(cx + .5, Y(b.l)); x.stroke();
      x.fillStyle = col;
      const yo = Y(b.o), yc = Y(b.c);
      x.fillRect(cx - bw/2, Math.min(yo, yc), bw, Math.max(1, Math.abs(yo - yc)));
    });
    const last = N(u.price), yl = clamp(Y(last), padT, padT + priceH);
    x.strokeStyle = C_AMBER; x.globalAlpha = .7; x.setLineDash([3, 3]);
    x.beginPath(); x.moveTo(padL, yl + .5); x.lineTo(W - padR, yl + .5); x.stroke(); x.setLineDash([]); x.globalAlpha = 1;
    x.fillStyle = C_AMBER; x.fillRect(W - padR + 2, yl - 8, padR - 4, 16);
    x.fillStyle = '#1a1a1a'; x.textAlign = 'center'; x.fillText(last.toFixed(2), W - padR / 2, yl);
    x.fillStyle = C_FAINT; x.textAlign = 'center'; x.textBaseline = 'alphabetic';
    const step = Math.max(1, Math.round(n / 5));
    for (let i = Math.floor(step / 2); i < n; i += step) x.fillText(barLabel(bars[i]), X(i), H - 3);
    if (st.hover >= 0 && st.hover < n){
      const cx = X(st.hover);
      x.strokeStyle = C_MUTED; x.globalAlpha = .6; x.beginPath(); x.moveTo(cx + .5, padT); x.lineTo(cx + .5, H - xH); x.stroke(); x.globalAlpha = 1;
    }
    if (ohlcEl){
      const b = (st.hover >= 0 && bars[st.hover]) ? bars[st.hover] : bars[n - 1];
      const dir = cls(b.c - b.o);
      ohlcEl.innerHTML = 'O <b>' + b.o.toFixed(2) + '</b>  H <b>' + b.h.toFixed(2) + '</b>  L <b>' + b.l.toFixed(2) + '</b>  C <b class="' + dir + '">' + b.c.toFixed(2) + '</b>  VOL <b>' + fmtVol(b.v || 0) + '</b>';
    }
  }
  canvas.addEventListener('mousemove', e => {
    const r = canvas.getBoundingClientRect(), n = st.bars.length; if (!n) return;
    st.hover = clamp(Math.floor((e.clientX - r.left - 6) / ((r.width - 64) / n)), 0, n - 1);
    paint();
  });
  canvas.addEventListener('mouseleave', () => { st.hover = -1; paint(); });
  return { load, paint, st };
}
function sparkline(cv, pts){
  const dpr = window.devicePixelRatio || 1;
  cv.width = 64 * dpr; cv.height = 18 * dpr;
  cv.style.width = '64px'; cv.style.height = '18px';
  const x = cv.getContext('2d'); x.setTransform(dpr, 0, 0, dpr, 0, 0);
  if (pts.length < 2) return;
  const hi = Math.max(...pts), lo = Math.min(...pts), sp = (hi - lo) || 1;
  x.strokeStyle = pts[pts.length-1] >= pts[0] ? C_UP : C_DOWN; x.lineWidth = 1; x.beginPath();
  pts.forEach((p, i) => { const px = i / (pts.length - 1) * 62 + 1, py = 16 - (p - lo) / sp * 14 + 1; i ? x.lineTo(px, py) : x.moveTo(px, py); });
  x.stroke();
}
const sparkPts = u => (S.candles[u.id] || []).map(r => N(r.c)).concat([N(u.price)]);

/* ================= header / tape / board ================= */
function renderClock(){
  $('#clock').textContent = ts();
  const open = marketOpen(), pill = $('#mkt-pill');
  const h = marketHour();
  const mins = open ? (24 - h) * 60 : ((8 - h + 24) % 24) * 60;
  const cd = Math.floor(mins / 60) + 'h';
  pill.className = 'pill ' + (open ? 'open' : 'closed');
  pill.textContent = open ? 'MARKET OPEN · closes in ~' + cd : 'MARKET CLOSED · opens in ~' + cd;
  $('#feed-state').textContent = open ? 'LIVE' : 'CLOSED';
  const c = composite();
  $('#idx-q').innerHTML = '<span class="name">MRX COMP</span><b>' + c.v.toFixed(2) + '</b>' + chipPct(c.chg);
  if (S.account) $('#cash').textContent = 'CASH ' + fmtP(S.account.cash);
  $('#foot-range').textContent = 'MRX ' + c.v.toFixed(2) + ' · ' + fmtPct(c.chg * 100) + ' today';
}

function buildTape(){
  const items = [{ n: 'MRX COMP', v: () => { const c = composite(); return [c.v.toFixed(2), c.chg]; } }]
    .concat(Object.keys(SECTORS).map(s => ({ n: SECTORS[s].toUpperCase(), v: () => { const t = sectorStats(s); return [fmtK(t.v), t.chg]; } })))
    .concat(S.listings.map(u => ({ n: u.ticker, v: () => [N(u.price).toFixed(2), dayChg(S.byT[u.ticker] || u)], go: u.ticker })));
  const html = items.map((it, i) => '<span class="ti" data-i="' + i + '"' + (it.go ? ' data-go="' + it.go + '"' : '') + '><span class="t">' + esc(it.n) + '</span><span class="v"></span> <span class="c"></span></span>').join('');
  $('#tape-track').innerHTML = html + html;
  $('#tape-track')._items = items;
  updateTape();
}
function updateTape(){
  const tr = $('#tape-track'), items = tr._items; if (!items) return;
  tr.querySelectorAll('.ti').forEach(el => {
    const it = items[+el.dataset.i % items.length];
    const [v, chg] = it.v();
    el.querySelector('.v').textContent = v;
    const c = el.querySelector('.c'); c.textContent = arrow(chg) + ' ' + fmtPct(chg * 100); c.className = 'c ' + cls(chg);
  });
}

function buildMovers(){
  const tb = $('#movers tbody');
  const list = S.listings.slice().sort((a, b) => mcap(b) - mcap(a));
  tb.innerHTML = list.map(u =>
    '<tr data-go="' + u.ticker + '" data-t="' + u.ticker + '"' + (u.ticker === S.sel ? ' class="sel"' : '') + '>' +
    '<td><span class="tk">' + esc(u.ticker) + '</span>' + (S.follows.has(u.id) ? ' <span class="dim">★</span>' : '') +
    '<br><span class="co-name">' + esc(u.company) + '</span></td>' +
    '<td class="c-last"></td><td class="c-chg"></td><td class="c-vol"></td><td class="c-mc"></td>' +
    '<td><canvas class="spark" width="64" height="18"></canvas></td></tr>').join('');
  tb.querySelectorAll('tr').forEach(tr => sparkline(tr.querySelector('canvas'), sparkPts(S.byT[tr.dataset.t])));
  $('#mkt-count').textContent = S.listings.length + ' LISTED';
  updateMovers();
}
function updateMovers(){
  document.querySelectorAll('#movers tbody tr').forEach(tr => {
    const u = S.byT[tr.dataset.t]; if (!u) return;
    const last = tr.querySelector('.c-last');
    const prev = last.textContent, cur = N(u.price).toFixed(2);
    last.textContent = cur;
    if (prev && prev !== cur){
      last.classList.remove('flash-up', 'flash-down'); void last.offsetWidth;
      last.classList.add(N(cur) > N(prev) ? 'flash-up' : 'flash-down');
    }
    tr.querySelector('.c-chg').innerHTML = chipPct(dayChg(u));
    tr.querySelector('.c-vol').textContent = fmtVol(u.day_vol);
    tr.querySelector('.c-mc').textContent = fmtK(mcap(u));
    tr.classList.toggle('sel', u.ticker === S.sel);
  });
}
function renderSectors(){
  $('#sectors tbody').innerHTML = Object.keys(SECTORS).map(s => {
    const t = sectorStats(s);
    return '<tr><td>' + SECTORS[s].toUpperCase() + ' <span class="co-name">' + t.list.length + ' listed</span></td>' +
      '<td>' + fmtK(t.v) + '</td><td>' + chipPct(t.chg) + '</td><td>' + chipPct(t.wk) + '</td>' +
      '<td><canvas class="spark sec-spark" data-s="' + s + '" width="64" height="18"></canvas></td></tr>';
  }).join('');
  document.querySelectorAll('.sec-spark').forEach(cv => {
    const list = S.listings.filter(u => u.sector === cv.dataset.s);
    if (!list.length) return;
    const n = Math.min(22, ...list.map(u => (S.candles[u.id] || []).length + 1));
    if (n < 2) return;
    const pts = [];
    for (let k = 0; k < n; k++){
      pts.push(list.reduce((a, u) => { const p = sparkPts(u); return a + p[p.length - n + k] * N(u.shares); }, 0));
    }
    sparkline(cv, pts);
  });
}

let miniChart = null;
function buildMini(){
  const u = S.byT[S.sel]; if (!u) return;
  $('#mini-co').innerHTML =
    '<div class="chartbar"><span class="tk" style="padding:0 6px">' + esc(u.ticker) + '</span>' +
    '<span class="dim" style="margin-right:8px">' + esc(u.company) + '</span><span class="c-px"></span>' +
    ['1D','1M','3M','ALL'].map(r => '<button class="rng" data-r="' + r + '" aria-pressed="' + (r === '1D') + '">' + r + '</button>').join('') +
    '<button class="rng" data-open="' + u.ticker + '" style="color:var(--amber)">OPEN LISTING</button>' +
    '<span class="ohlc"></span></div><canvas id="chart-mini" style="width:100%;height:340px;display:block;cursor:crosshair"></canvas>';
  miniChart = chartify($('#chart-mini'), $('#mini-co .ohlc'), () => S.byT[S.sel]);
  $('#mini-co').querySelectorAll('[data-r]').forEach(b => b.addEventListener('click', () => {
    miniChart.st.range = b.dataset.r;
    $('#mini-co').querySelectorAll('[data-r]').forEach(x => x.setAttribute('aria-pressed', x === b));
    miniChart.load();
  }));
  $('#mini-co').querySelector('[data-open]').addEventListener('click', () => go(u.ticker));
  miniChart.load();
  updateMini();
}
function updateMini(){
  const u = S.byT[S.sel], px = $('#mini-co .c-px');
  if (!u || !px) return;
  px.innerHTML = '<b style="font-size:15px">' + fmtP(u.price) + '</b> ' + chipPct(dayChg(u));
  if (miniChart){ miniChart.st.bars.length ? miniChart.paint() : miniChart.load(); }
}

/* ================= leaderboards ================= */
function renderLb(){
  const rows = (list, f) => list.map((u, i) => '<tr data-go="' + u.ticker + '"><td>' + (i + 1) + '  <span class="tk">' + esc(u.ticker) + '</span> <span class="co-name">' + esc(u.display_name) + '</span></td>' + f(u) + '</tr>').join('');
  const g = S.listings.slice().sort((a, b) => dayChg(b) - dayChg(a));
  const t = S.listings.slice().sort((a, b) => N(b.day_vol) - N(a.day_vol));
  const m = S.listings.slice().sort((a, b) => mcap(b) - mcap(a));
  $('#lb').innerHTML =
    '<div class="panel"><h2>TOP GAINERS <span class="r">TODAY</span></h2><table><thead><tr><th>TICKER</th><th>LAST</th><th>CHG%</th></tr></thead><tbody>' +
    rows(g.slice(0, 8), u => '<td>' + N(u.price).toFixed(2) + '</td><td>' + chipPct(dayChg(u)) + '</td>') + '</tbody></table></div>' +
    '<div class="panel"><h2>BIGGEST CRASHES <span class="r">TODAY</span></h2><table><thead><tr><th>TICKER</th><th>LAST</th><th>CHG%</th></tr></thead><tbody>' +
    rows(g.slice(-8).reverse(), u => '<td>' + N(u.price).toFixed(2) + '</td><td>' + chipPct(dayChg(u)) + '</td>') + '</tbody></table></div>' +
    '<div class="panel"><h2>HIGHEST MARKET CAP</h2><table><thead><tr><th>TICKER</th><th>MCAP</th><th>WEEK%</th></tr></thead><tbody>' +
    rows(m.slice(0, 8), u => '<td>' + fmtK(mcap(u)) + '</td><td>' + chipPct(weekChg(u)) + '</td>') + '</tbody></table></div>' +
    '<div class="panel"><h2>MOST TRADED <span class="r">VOLUME</span></h2><table><thead><tr><th>TICKER</th><th>VOL</th><th>CHG%</th></tr></thead><tbody>' +
    rows(t.slice(0, 8), u => '<td>' + fmtVol(u.day_vol) + '</td><td>' + chipPct(dayChg(u)) + '</td>') + '</tbody></table></div>';
}

/* ================= predictions ================= */
async function renderPred(){
  const nowISO = new Date().toISOString();
  const [mk, pools, settledStakes] = await Promise.all([
    sb.from('pred_markets').select('*').eq('status', 'open').gt('deadline', nowISO).order('deadline', { ascending: true }).limit(20),
    sb.from('pred_pools').select('*'),
    sb.from('pred_stakes').select('*').eq('user_id', session.user.id).order('id', { ascending: false }).limit(30),
  ]);
  const poolBy = Object.fromEntries((pools.data || []).map(p => [p.market_id, p]));
  S.stakes = settledStakes.data || [];
  const open = mk.data || [];
  const mineByMarket = Object.fromEntries(S.stakes.map(s => [s.market_id, s]));

  $('#pmarkets').innerHTML = open.length ? open.map(m => {
    const u = S.byId[m.listing_id];
    const pool = poolBy[m.id] || { yes_pool: 0, no_pool: 0 };
    const dl = new Date(m.deadline);
    const when = dl.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' });
    const own = u && u.user_id === session.user.id;
    const mine = mineByMarket[m.id];
    let controls;
    if (own) controls = '<span class="own">Your guidance. You cannot bet on yourself.</span>';
    else if (mine) controls = '<span class="dim">Your position: ' + mine.side + ' ' + fmtP(mine.amount) + '</span>';
    else controls =
      '<input class="stake" type="number" min="1" max="1000" value="25" aria-label="Stake">' +
      '<button class="btn-yes" data-side="YES">YES</button>' +
      '<button class="btn-no" data-side="NO">NO</button>';
    return '<div class="pm" data-mid="' + m.id + '"><div class="q">' +
      (u ? '<span class="tk dim" data-go="' + esc(u.ticker) + '">' + esc(u.ticker) + '</span>  ' : '') + esc(m.question) + '</div>' +
      '<div class="row">' + controls +
      '<span class="meta">YES pool ' + fmtK(pool.yes_pool) + ' · NO pool ' + fmtK(pool.no_pool) + ' · settles ' + when + '</span></div>' +
      '<div class="ordmsg"></div></div>';
  }).join('') : '<div class="empty">No open markets. A market opens automatically whenever someone issues guidance.</div>';

  $('#pmarkets').querySelectorAll('.pm button[data-side]').forEach(b => b.addEventListener('click', async () => {
    const box = b.closest('.pm'), amt = Number(box.querySelector('.stake').value);
    box.querySelector('.ordmsg').textContent = 'Placing stake…';
    const res = await api('predict', { market_id: Number(box.dataset.mid), side: b.dataset.side, amount: amt });
    box.querySelector('.ordmsg').textContent = res.error || ('Position taken: ' + b.dataset.side + ' ' + fmtP(amt) + '.');
    if (!res.error){ await refreshLite(); renderPred(); }
  }));

  const openIds = new Set(open.map(m => m.id));
  const openMine = S.stakes.filter(s => s.payout == null && openIds.has(s.market_id));
  $('#ppos').innerHTML = openMine.length ? openMine.map(s =>
    '<div class="pos">' + s.side + ' ' + fmtP(s.amount) + ' · market #' + s.market_id + '</div>').join('')
    : '<div class="empty">No open positions. Back someone’s follow-through, or fade it.</div>';

  const done = S.stakes.filter(s => s.payout != null);
  $('#psettled').innerHTML = done.length ? done.slice(0, 12).map(s => {
    const net = N(s.payout) - N(s.amount);
    return '<div class="pos"><span class="' + (net >= 0 ? 'up' : 'down') + '">' + (net >= 0 ? '+' : MINUS) + '£' + Math.abs(net).toFixed(2) + '</span> · ' + s.side + ' ' + fmtP(s.amount) + ' · paid ' + fmtP(s.payout) + '</div>';
  }).join('') : '<div class="empty">Nothing settled yet. Winners split the losing pool, stake-weighted.</div>';
}

/* ================= new listings ================= */
function renderIpo(){
  const humans = S.listings.filter(u => !u.is_bot).sort((a, b) => new Date(b.listed_at) - new Date(a.listed_at)).slice(0, 6);
  const card = u => {
    const perf = (N(u.price) - 10) / 10;
    const days = Math.max(1, Math.round((Date.now() - new Date(u.listed_at)) / 864e5));
    return '<div class="panel prospectus"><h2>' + (u.user_id === session.user.id ? 'YOUR LISTING' : 'LISTING') + ' <span class="r">DAY ' + days + '</span></h2>' +
      '<div class="sec"><div class="k">ISSUER</div><div class="v" style="cursor:pointer" data-go="' + esc(u.ticker) + '">' + esc(u.company) + ' (' + esc(u.ticker) + ') · CEO: ' + esc(u.display_name) + '</div></div>' +
      '<div class="sec"><div class="k">SECTOR</div><div class="v">' + SECTORS[u.sector] + '</div></div>' +
      '<div class="sec"><div class="k">PERFORMANCE SINCE LISTING</div><div class="v">' + chipPct(perf) + ' · listed @ £10.00, now ' + fmtP(u.price) + '</div></div>' +
      (u.pitch ? '<div class="sec"><div class="k">PITCH</div><div class="prose">' + esc(u.pitch) + '</div></div>' : '') +
      (u.outlook ? '<div class="sec"><div class="k">OUTLOOK</div><div class="prose">' + esc(u.outlook) + '</div></div>' : '') +
      (u.risks?.length ? '<div class="sec"><div class="k">RISK FACTORS</div><ul class="risk">' + u.risks.map(r => '<li>' + esc(r) + '</li>').join('') + '</ul></div>' : '') +
      '</div>';
  };
  $('#ipos').innerHTML = (humans.length ? humans.map(card).join('') : '') +
    '<div class="panel prospectus"><h2>HOUSE LISTINGS <span class="r">' + S.listings.filter(u => u.is_bot).length + ' ACTIVE</span></h2>' +
    '<div class="sec"><div class="prose">The tickers marked as house listings are simulated participants run by the exchange. They trade under the same rules, keep the floor liquid, and give the feed a pulse at 3 a.m. Real members joining by IPO appear here on listing day.</div></div></div>';
}

/* ================= portfolio ================= */
async function renderPf(){
  const [tr, dv] = await Promise.all([
    sb.from('trades').select('*').eq('user_id', session.user.id).order('id', { ascending: false }).limit(14),
    sb.from('dividends').select('*').eq('user_id', session.user.id).order('id', { ascending: false }).limit(10),
  ]);
  S.trades = tr.data || []; S.dividends = dv.data || [];
  const ids = Object.keys(S.holdings);
  let hv = 0, dayPl = 0;
  ids.forEach(id => { const u = S.byId[id], h = S.holdings[id]; if (!u) return; hv += h.shares * N(u.price); dayPl += h.shares * (N(u.price) - N(u.prev_close)); });
  $('#pf-head').innerHTML =
    '<div><div class="k">CASH</div><div class="v">' + fmtP(S.account?.cash || 0) + '</div></div>' +
    '<div><div class="k">HOLDINGS</div><div class="v">' + fmtP(hv) + '</div></div>' +
    '<div><div class="k">TOTAL</div><div class="v">' + fmtP(N(S.account?.cash) + hv) + '</div></div>' +
    '<div><div class="k">DAY P&L</div><div class="v ' + cls(dayPl) + '">' + (dayPl >= 0 ? '+' : MINUS) + '£' + Math.abs(dayPl).toFixed(2) + '</div></div>';
  $('#pf-hold tbody').innerHTML = ids.map(id => {
    const u = S.byId[id], h = S.holdings[id]; if (!u) return '';
    const avg = N(h.cost) / h.shares, pl = h.shares * N(u.price) - N(h.cost), plp = N(h.cost) ? pl / N(h.cost) : 0;
    return '<tr data-go="' + esc(u.ticker) + '"><td><span class="tk">' + esc(u.ticker) + '</span> <span class="co-name">' + esc(u.company) + '</span></td>' +
      '<td>' + h.shares + '</td><td>' + fmtP(avg) + '</td><td>' + fmtP(u.price) + '</td><td>' + fmtP(h.shares * N(u.price)) + '</td>' +
      '<td class="' + cls(pl) + '">' + (pl >= 0 ? '+' : MINUS) + '£' + Math.abs(pl).toFixed(2) + '</td><td>' + chipPct(plp) + '</td></tr>';
  }).join('');
  $('#pf-empty').hidden = ids.length > 0;
  $('#pf-div').innerHTML = S.dividends.length ? S.dividends.map(d => {
    const u = S.byId[d.listing_id];
    return '<div class="pos"><span class="up">+£' + N(d.amount).toFixed(2) + '</span> · ' + esc(u?.ticker || '?') + ' · £' + N(d.per_share).toFixed(2) + '/sh</div>';
  }).join('') : '<div class="empty">No dividends yet. Long streaks pay the patient: 30 days of consistency triggers a payout to holders.</div>';
  $('#pf-hist').innerHTML = S.trades.length ? S.trades.map(t => {
    const u = S.byId[t.listing_id];
    return '<div class="pos">' + ts(t.ts) + ' · <span class="' + (t.side === 'buy' ? 'up' : 'down') + '">' + t.side.toUpperCase() + '</span> ' + t.qty + ' ' + esc(u?.ticker || '?') + ' @ ' + fmtP(t.price) + '</div>';
  }).join('') : '<div class="empty">No trades yet.</div>';
}

/* ================= company page ================= */
let coChart = null, coTicker = null;

function botEarnings(u){
  const r = mulberry32(hash(u.ticker + '/er'));
  const c = N(u.bot_consistency);
  return {
    sessions: Math.round(6 + c * 18 + r() * 4),
    hours: Math.round(10 + c * 50 + r() * 10),
    goals: Math.round(1 + c * 4 + r()) + ' of ' + Math.round(3 + r() * 2 + c * 2),
    misses: Math.round((1 - c) * 6),
  };
}
async function humanEarnings(u){
  const from = new Date(Date.now() - 30 * 864e5).toISOString().slice(0, 10);
  const { data } = await sb.from('actions').select('kind').eq('listing_id', u.id).gte('day', from);
  const n = k => (data || []).filter(a => a.kind === k).length;
  return { sessions: n('session'), hours: n('deep_work') * 2, goals: n('goal') + ' hit · ' + n('miss') + ' missed', misses: n('miss') };
}

async function renderCo(tickr, mount){
  const u = S.byT[tickr];
  if (!u){ mount.innerHTML = '<div class="loading">Unknown ticker.</div>'; return; }
  const isMe = u.user_id === session.user.id;
  mount.innerHTML = '<div class="loading">Pulling the book on ' + esc(tickr) + '…</div>';

  const [cm, rc, myRc, gRows, rep] = await Promise.all([
    sb.from('comments').select('*').eq('listing_id', u.id).order('id', { ascending: false }).limit(20),
    sb.from('reaction_counts').select('*').eq('listing_id', u.id).maybeSingle(),
    sb.from('reactions').select('stance').eq('listing_id', u.id).eq('user_id', session.user.id).maybeSingle(),
    sb.from('guidance').select('*').eq('listing_id', u.id).order('id', { ascending: false }).limit(5),
    u.is_bot ? Promise.resolve(botEarnings(u)) : humanEarnings(u),
  ]);
  const comments = cm.data || [];
  const reacts = rc.data || { bull: 0, hold: 0, bear: 0 };
  const myStance = myRc.data?.stance || null;
  const guid = gRows.data || [];
  const gOpen = guid.find(g => g.status === 'open');
  const hc = S.holders[u.id] || { holders: 0, held: 0 };
  const conf = u.is_bot ? Math.round(N(u.bot_consistency) * 88 + 6) : u.confidence;
  const rating = conf >= 75 ? 'STRONG BUY' : conf >= 58 ? 'BUY' : conf >= 42 ? 'HOLD' : conf >= 28 ? 'SELL' : 'STRONG SELL';
  const myPos = S.holdings[u.id];
  const monthAgo = (S.candles[u.id] || [])[0];
  const perf = monthAgo ? (N(u.price) - N(monthAgo.c)) / N(monthAgo.c) : (N(u.price) - 10) / 10;
  const following = S.follows.has(u.id);
  const canComment = !!myPos?.shares;
  const waiting = isMe && marketOpen() && S.myActionsToday === 0 && hc.holders > 0;

  mount.innerHTML =
    '<div class="co-head"><h1>' + esc(u.company) + '</h1>' +
    '<span class="sub">' + esc(u.ticker) + ' · ' + SECTORS[u.sector] + ' · CEO: ' + esc(u.display_name) + (u.is_bot ? ' · house listing' : '') + '</span>' +
    '<span class="pill rating">' + rating + ' · CONFIDENCE ' + conf + '/100</span>' +
    (!isMe ? '<button class="follow-btn" aria-pressed="' + following + '">' + (following ? 'Following' : 'Follow') + '</button>' : '') +
    '</div>' +
    '<div class="quote"><span class="px c-px">' + fmtP(u.price) + '</span><span class="chg c-chg">' + chipPct(dayChg(u)) + '</span>' +
    '<span class="kv">OPEN<b>' + fmtP(u.day_open) + '</b></span><span class="kv">HIGH<b>' + fmtP(u.day_high) + '</b></span>' +
    '<span class="kv">LOW<b>' + fmtP(u.day_low) + '</b></span><span class="kv">PREV<b>' + fmtP(u.prev_close) + '</b></span>' +
    '<span class="kv">VOL<b class="c-vol">' + fmtVol(u.day_vol) + '</b></span><span class="kv">MCAP<b class="c-mc">' + fmtK(mcap(u)) + '</b></span></div>' +
    '<div class="grid-co"><div style="display:flex;flex-direction:column;gap:12px;min-width:0">' +
    '<div class="panel chartbox"><div class="chartbar">' +
    ['1D','1M','3M','ALL'].map(r => '<button class="rng" data-r="' + r + '" aria-pressed="' + (r === '1D') + '">' + r + '</button>').join('') +
    '<span class="ohlc"></span></div>' +
    '<canvas class="co-canvas" style="width:100%;height:380px;display:block;cursor:crosshair"></canvas></div>' +
    (isMe ?
      '<div class="panel"><h2>DESK ACTIONS <span class="r">MOVE YOUR OWN TAPE</span></h2>' +
      '<div class="actions">' +
      '<button data-act="session">Log gym session</button>' +
      '<button data-act="deep_work">Log deep work</button>' +
      '<button data-act="goal">Record goal hit</button>' +
      '<button data-act="miss" class="act-neg">Admit a miss</button></div>' +
      '<div class="guide-form">' + (gOpen ?
        '<span class="dim">Active guidance:</span> <b>' + gOpen.done + ' of ' + gOpen.target + ' sessions</b> <span class="dim">by Sunday close</span>' :
        '<span class="dim">Issue guidance:</span> <input type="number" id="g-n" min="1" max="14" value="5"> <span class="dim">gym sessions by Sunday</span> <button id="g-issue">Publish guidance</button>') +
      '</div><div class="ordmsg" id="act-msg" style="padding:0 10px 8px"></div></div>' : '') +
    '<div class="panel"><h2>ORDER TICKET</h2><div class="order">' +
    '<input type="number" class="o-qty" min="1" max="10000" value="10" aria-label="Quantity">' +
    '<button class="btn-buy" data-side="buy">Buy ' + esc(u.ticker) + '</button>' +
    '<button class="btn-sell" data-side="sell">Sell</button>' +
    '<span class="dim">@ market · <span class="c-px2">' + fmtP(u.price) + '</span></span>' +
    '<span class="dim" style="margin-left:auto">' + (myPos ? 'You hold ' + myPos.shares + ' sh @ avg ' + fmtP(N(myPos.cost) / myPos.shares) : 'No position') + '</span>' +
    '<div class="ordmsg"></div></div></div>' +
    '<div class="panel"><h2>EARNINGS REPORT <span class="r">LAST 30 DAYS · AUTO-FILED</span></h2>' +
    '<table class="report"><tbody>' +
    '<tr><td>Gym sessions completed</td><td>' + rep.sessions + '</td></tr>' +
    '<tr><td>Deep work / study hours</td><td>' + rep.hours + '</td></tr>' +
    '<tr><td>Goals</td><td>' + rep.goals + '</td></tr>' +
    '<tr><td>Best streak</td><td>' + u.streak + ' days</td></tr>' +
    '<tr><td>Stock performance</td><td>' + chipPct(perf) + '</td></tr>' +
    '<tr><td>Dividend</td><td>' + (u.streak >= 30 ? 'paying £0.02/sh daily' : 'accruing') + '</td></tr></tbody></table>' +
    '<div class="react"><span class="dim" style="align-self:center">Street view:</span>' +
    '<button data-react="bull" aria-pressed="' + (myStance === 'bull') + '">Bullish ' + reacts.bull + '</button>' +
    '<button data-react="hold" aria-pressed="' + (myStance === 'hold') + '">Hold ' + reacts.hold + '</button>' +
    '<button data-react="bear" aria-pressed="' + (myStance === 'bear') + '">Bearish ' + reacts.bear + '</button></div></div>' +
    '</div><div style="display:flex;flex-direction:column;gap:12px">' +
    '<div class="panel"><h2>FUNDAMENTALS</h2><div class="kv-grid">' +
    '<div><div class="k">MARKET CAP</div><div class="v">' + fmtK(mcap(u)) + '</div></div>' +
    '<div><div class="k">SHARES OUT</div><div class="v">' + N(u.shares).toLocaleString('en-GB') + '</div></div>' +
    '<div><div class="k">INVESTORS</div><div class="v">' + hc.holders + '</div></div>' +
    '<div><div class="k">WEEK</div><div class="v">' + chipPct(weekChg(u)) + '</div></div>' +
    '<div><div class="k">ALL-TIME HIGH</div><div class="v">' + fmtP(u.ath) + '</div></div>' +
    '<div><div class="k">CURRENT STREAK</div><div class="v">' + u.streak + ' days</div></div>' +
    '<div style="grid-column:1/-1"><div class="k">INVESTOR CONFIDENCE · ' + conf + '/100</div><div class="gauge"><i style="width:' + conf + '%"></i></div></div>' +
    '</div></div>' +
    '<div class="panel"><h2>GUIDANCE</h2>' +
    (gOpen ?
      '<div class="gline"><div class="prose">“I will complete ' + gOpen.target + ' gym sessions this week.”</div><div class="dim">' + gOpen.done + ' of ' + gOpen.target + ' logged · a beat pays a surge, a miss gets punished</div></div>' :
      '<div class="gline"><div class="prose">No active guidance. The market only rewards public promises.</div></div>') +
    guid.filter(g => g.status !== 'open').slice(0, 4).map(g =>
      '<div class="gline"><span class="' + (g.status === 'beat' ? 'up' : 'down') + '">' + g.status.toUpperCase() + '</span> · ' + g.done + ' of ' + g.target + ' sessions</div>').join('') +
    '</div>' +
    '<div class="panel"><h2>SHAREHOLDERS <span class="r">' + hc.holders + ' ON REGISTER</span></h2>' +
    (waiting ? '<div class="press">' + hc.holders + ' shareholder' + (hc.holders === 1 ? ' is' : 's are') + ' waiting on today’s session.</div>' : '') +
    '<div class="comments">' + (comments.length ? comments.map(c =>
      '<div class="cm"><div class="who">' + esc(c.author) + ' · ' + c.held + ' sh · ' + ts(c.created_at) + '</div><div class="prose">' + esc(c.body) + '</div></div>').join('')
      : '<div class="empty">No comments on the register yet.</div>') + '</div>' +
    (canComment ? '<div class="composer"><input maxlength="280" placeholder="Say it to their face; you own the stock." aria-label="Comment"><button>Post</button></div>' :
      '<div class="empty" style="border-top:1px solid var(--line)">Shareholders only: buy at least one share to comment.</div>') +
    '</div></div></div>';

  coTicker = tickr;
  const cvs = mount.querySelector('.co-canvas');
  coChart = chartify(cvs, mount.querySelector('.ohlc'), () => S.byT[tickr]);
  mount.querySelectorAll('[data-r]').forEach(b => b.addEventListener('click', () => {
    coChart.st.range = b.dataset.r;
    mount.querySelectorAll('[data-r]').forEach(x => x.setAttribute('aria-pressed', x === b));
    coChart.load();
  }));
  coChart.load();

  mount.querySelectorAll('.order button[data-side]').forEach(b => b.addEventListener('click', async () => {
    const msg = mount.querySelector('.order .ordmsg');
    msg.textContent = 'Routing order…';
    const res = await api('trade', { ticker: tickr, side: b.dataset.side, qty: Number(mount.querySelector('.o-qty').value) });
    msg.textContent = res.error || ('Filled: ' + (res.qty || '') + ' ' + tickr + ' @ ' + fmtP(res.price) + '.');
    if (!res.error){ await refreshLite(); renderCo(tickr, mount); }
  }));
  mount.querySelectorAll('[data-react]').forEach(b => b.addEventListener('click', async () => {
    const stance = b.getAttribute('aria-pressed') === 'true' ? 'clear' : b.dataset.react;
    await api('react', { ticker: tickr, stance });
    renderCo(tickr, mount);
  }));
  const fb = mount.querySelector('.follow-btn');
  if (fb) fb.addEventListener('click', async () => {
    if (S.follows.has(u.id)){ await sb.from('follows').delete().eq('follower', session.user.id).eq('listing_id', u.id); S.follows.delete(u.id); }
    else { await sb.from('follows').insert({ follower: session.user.id, listing_id: u.id }); S.follows.add(u.id); }
    renderCo(tickr, mount);
  });
  const composer = mount.querySelector('.composer');
  if (composer) composer.querySelector('button').addEventListener('click', async () => {
    const input = composer.querySelector('input');
    const res = await api('comment', { ticker: tickr, body: input.value });
    if (res.error) input.value = res.error; else { input.value = ''; renderCo(tickr, mount); }
  });
  if (isMe){
    mount.querySelectorAll('[data-act]').forEach(b => b.addEventListener('click', async () => {
      $('#act-msg').textContent = 'Printing to the tape…';
      const res = await api('action', { kind: b.dataset.act });
      $('#act-msg').textContent = res.error || (res.cash_earned ? 'Logged. £' + res.cash_earned + ' earned.' : 'Logged.');
      if (!res.error){
        if (b.dataset.act === 'session') S.myActionsToday++;
        delete tickCache[u.id];
        await refreshLite(); renderCo(tickr, mount);
      }
    }));
    const gi = mount.querySelector('#g-issue');
    if (gi) gi.addEventListener('click', async () => {
      const res = await api('guidance', { target: Number(mount.querySelector('#g-n').value) });
      $('#act-msg').textContent = res.error || 'Guidance published. The market is watching.';
      if (!res.error){ await loadCore(); renderCo(tickr, mount); }
    });
  }
}

/* ================= views / navigation ================= */
function renderLive(){
  updateTape(); renderClock();
  if (S.view === 'mkt'){ updateMovers(); updateMini(); renderSectors(); }
  if (S.view === 'lb') renderLb();
}
async function renderAllViews(){
  renderClock(); updateTape();
  if (S.view === 'mkt'){ buildMovers(); renderSectors(); if (!$('#mini-co').innerHTML) buildMini(); else updateMini(); }
  if (S.view === 'lb') renderLb();
  if (S.view === 'pred') renderPred();
  if (S.view === 'ipo') renderIpo();
  if (S.view === 'pf') renderPf();
  if (S.view === 'co') renderCo(S.sel, $('#view-co'));
  if (S.view === 'me' && S.myListing) renderCo(S.myListing.ticker, $('#view-me'));
}
function showView(v){
  S.view = v;
  showOnly(v);
  document.querySelectorAll('nav button').forEach(b => b.setAttribute('aria-current', b.dataset.view === v));
  renderAllViews();
}
function go(tickr){
  if (S.myListing && tickr === S.myListing.ticker){ showView('me'); return; }
  S.sel = tickr;
  showView('co');
  window.scrollTo({ top: 0 });
}
document.addEventListener('click', e => {
  const g = e.target.closest('[data-go]');
  if (g && !e.target.closest('button')) go(g.dataset.go);
});
$('#nav').addEventListener('click', e => {
  const b = e.target.closest('button[data-view]');
  if (b) showView(b.dataset.view);
});

/* ================= app entry ================= */
let started = false;
async function enterApp(){
  await loadCore();
  $('#nav').hidden = false; $('#tape').hidden = false;
  $('#feed').innerHTML = S.events.map(feedHTML).join('');
  S.sel = S.myListing.ticker;
  buildTape();
  document.body.classList.toggle('closed', !marketOpen());

  const h = decodeURIComponent(location.hash.slice(1));
  if (h && S.byT[h]) go(h);
  else if (h && document.getElementById('view-' + h) && !['auth','onboard','co'].includes(h)) showView(h);
  else showView('mkt');

  if (started) return;
  started = true;
  setInterval(renderClock, 1000);
  setInterval(refreshLite, 20000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refreshLite(); });
  window.addEventListener('resize', () => { if (miniChart) miniChart.paint(); if (coChart) coChart.paint(); });

  try {
    sb.channel('mx')
      .on('postgres_changes', { event: 'INSERT', schema: 'public', table: 'events' }, p => pushEvent(p.new))
      .on('postgres_changes', { event: 'UPDATE', schema: 'public', table: 'listings' }, p => {
        const u = S.byId[p.new.id];
        if (u) Object.assign(u, p.new);
        renderLive();
      })
      .subscribe();
  } catch { /* realtime unavailable: polling covers it */ }
}

boot();
