import { createClient } from '@supabase/supabase-js';

const URL_ = process.env.SUPABASE_URL;
const ANON = process.env.SUPABASE_ANON_KEY;
const SERVICE = process.env.SUPABASE_SERVICE_ROLE_KEY;
export const MARKET_TZ = process.env.MARKET_TZ || 'Europe/London';

export function admin() {
  return createClient(URL_, SERVICE, { auth: { persistSession: false } });
}

/** Verify the caller's Supabase JWT. Returns { user } or { errorResponse }. */
export async function requireUser(req) {
  const token = (req.headers.get('authorization') || '').replace(/^Bearer\s+/i, '');
  if (!token) return { errorResponse: json({ error: 'Not signed in.' }, 401) };
  const anonClient = createClient(URL_, ANON, { auth: { persistSession: false } });
  const { data, error } = await anonClient.auth.getUser(token);
  if (error || !data?.user) return { errorResponse: json({ error: 'Session expired. Sign in again.' }, 401) };
  return { user: data.user };
}

export function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json', 'cache-control': 'no-store' },
  });
}

export async function readJson(req, maxBytes = 4096) {
  const text = await req.text();
  if (text.length > maxBytes) throw new Error('payload too large');
  return JSON.parse(text || '{}');
}

/* ---------------- market clock (all decisions in MARKET_TZ) ---------------- */

function tzParts(date = new Date()) {
  const fmt = new Intl.DateTimeFormat('en-GB', {
    timeZone: MARKET_TZ, hour12: false,
    year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit',
  });
  const p = Object.fromEntries(fmt.formatToParts(date).map(x => [x.type, x.value]));
  return { day: `${p.year}-${p.month}-${p.day}`, hour: Number(p.hour) % 24 };
}
export function marketDay(date) { return tzParts(date).day; }
export function marketHour(date) { return tzParts(date).hour; }
export function marketOpen(date) { return marketHour(date) >= 8; } // 08:00 → 00:00

/** End of the current week (Sunday 23:59) as an ISO timestamp, in MARKET_TZ terms. */
export function endOfWeekISO() {
  const now = new Date();
  // walk forward to the market-tz Sunday, then pin to 23:59 UTC-equivalent of that tz day
  for (let i = 0; i < 8; i++) {
    const d = new Date(now.getTime() + i * 864e5);
    const wd = new Intl.DateTimeFormat('en-GB', { timeZone: MARKET_TZ, weekday: 'short' }).format(d);
    if (wd === 'Sun') {
      const day = marketDay(d);
      // 23:59 in MARKET_TZ expressed via a locale round-trip is overkill here;
      // the deadline check runs hourly, so end-of-day UTC on that date is close enough.
      return new Date(`${day}T23:59:00Z`).toISOString();
    }
  }
  return new Date(now.getTime() + 7 * 864e5).toISOString();
}

/* ---------------- price engine ---------------- */

export const round2 = x => Math.round(x * 100) / 100;

/**
 * Apply a fractional move to a listing, record the tick, update day stats.
 * Server-side only; the client never supplies prices.
 */
export async function applyMove(db, listing, frac, vol = 0) {
  const px = Math.max(0.5, round2(listing.price * (1 + frac)));
  const { error } = await db.from('listings').update({
    price: px,
    day_high: Math.max(Number(listing.day_high), px),
    day_low: Math.min(Number(listing.day_low), px),
    day_vol: Number(listing.day_vol) + vol,
    ath: Math.max(Number(listing.ath), px),
  }).eq('id', listing.id);
  if (error) throw error;
  await db.from('ticks').insert({ listing_id: listing.id, price: px, vol });
  return px;
}

export async function postEvent(db, { ticker = null, body, move = null, kind = 'wire' }) {
  await db.from('events').insert({ ticker, body: body.slice(0, 300), move, kind });
}

/* ---------------- parimutuel settlement ---------------- */

/** Settle a prediction market. Winners get their stake back plus a pro-rata
 *  share of the losing pool. One-sided markets are voided and refunded. */
export async function settleMarket(db, market, outcome) {
  const { data: stakes } = await db.from('pred_stakes').select('*').eq('market_id', market.id);
  const yes = (stakes || []).filter(s => s.side === 'YES');
  const no = (stakes || []).filter(s => s.side === 'NO');
  const sum = a => a.reduce((t, s) => t + Number(s.amount), 0);

  if (!yes.length || !no.length) {
    for (const s of stakes || []) {
      await creditCash(db, s.user_id, Number(s.amount));
      await db.from('pred_stakes').update({ payout: Number(s.amount) }).eq('id', s.id);
    }
    await db.from('pred_markets').update({ status: 'void', outcome }).eq('id', market.id);
    return;
  }
  const winners = outcome === 'YES' ? yes : no;
  const losePool = outcome === 'YES' ? sum(no) : sum(yes);
  const winPool = sum(winners);
  for (const s of stakes || []) {
    const won = s.side === outcome;
    const payout = won ? round2(Number(s.amount) + (Number(s.amount) / winPool) * losePool) : 0;
    if (payout > 0) await creditCash(db, s.user_id, payout);
    await db.from('pred_stakes').update({ payout }).eq('id', s.id);
  }
  await db.from('pred_markets').update({ status: 'settled', outcome }).eq('id', market.id);
}

export async function creditCash(db, userId, amount) {
  const { data: acct } = await db.from('accounts').select('cash').eq('user_id', userId).single();
  if (!acct) return;
  await db.from('accounts').update({ cash: round2(Number(acct.cash) + amount) }).eq('user_id', userId);
}

/** Resolve a guidance row as beat or miss: price shock, feed, linked market. */
export async function resolveGuidance(db, g, listing, beat) {
  const frac = beat ? 0.06 + Math.random() * 0.03 : -(0.07 + Math.random() * 0.03);
  await applyMove(db, listing, frac, Math.round(listing.shares * 0.02));
  await db.from('guidance').update({ status: beat ? 'beat' : 'miss' }).eq('id', g.id);
  await db.from('listings').update(beat
    ? { beats: listing.beats + 1, confidence: Math.min(100, listing.confidence + 6) }
    : { misses: listing.misses + 1, confidence: Math.max(0, listing.confidence - 8) }
  ).eq('id', listing.id);
  await postEvent(db, {
    ticker: listing.ticker,
    body: beat
      ? `${listing.display_name} beats guidance (${g.target} sessions); shares gap up.`
      : `${listing.display_name} misses guidance (${g.done} of ${g.target} sessions); the market punishes it.`,
    move: frac,
  });
  if (beat) await creditCash(db, listing.user_id, 40);
  const { data: mkts } = await db.from('pred_markets').select('*')
    .eq('guidance_id', g.id).eq('status', 'open');
  for (const m of mkts || []) await settleMarket(db, m, beat ? 'YES' : 'NO');
}
