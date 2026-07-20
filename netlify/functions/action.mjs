import { admin, requireUser, json, readJson, applyMove, postEvent, marketDay, marketOpen, creditCash, resolveGuidance } from './_lib/core.mjs';

const KINDS = { session: 1, deep_work: 1, goal: 1, miss: 1 };
const DAILY_CAP = { session: 3, deep_work: 3, goal: 2, miss: 3 };

export default async (req) => {
  if (req.method !== 'POST') return json({ error: 'POST only.' }, 405);
  const { user, errorResponse } = await requireUser(req);
  if (errorResponse) return errorResponse;

  let b;
  try { b = await readJson(req); } catch { return json({ error: 'Bad request body.' }, 400); }
  const kind = String(b.kind || '');
  if (!KINDS[kind]) return json({ error: 'Unknown action.' }, 400);

  const db = admin();
  const { data: listing } = await db.from('listings').select('*').eq('user_id', user.id).single();
  if (!listing) return json({ error: 'You are not listed yet.' }, 400);

  const day = marketDay();
  const { count } = await db.from('actions')
    .select('*', { count: 'exact', head: true })
    .eq('listing_id', listing.id).eq('day', day).eq('kind', kind);
  if ((count || 0) >= DAILY_CAP[kind]) {
    return json({ error: 'Daily limit reached for that action. The tape resets at the opening bell.' }, 429);
  }
  const nToday = count || 0;

  await db.from('actions').insert({ listing_id: listing.id, kind, day });

  const afterHours = !marketOpen();
  const suffix = afterHours ? ' (after hours)' : '';
  let frac = 0, body = '', cash = 0;
  const upd = {};

  if (kind === 'session') {
    frac = (0.018 + Math.random() * 0.014) * Math.pow(0.45, nToday);
    body = `${listing.display_name} logs a gym session; the desk takes notice.${suffix}`;
    cash = nToday === 0 ? 12 : 4;
  } else if (kind === 'deep_work') {
    frac = (0.008 + Math.random() * 0.008) * Math.pow(0.55, nToday);
    body = `${listing.display_name} logs two hours of focused work.${suffix}`;
    cash = nToday === 0 ? 6 : 2;
  } else if (kind === 'goal') {
    frac = 0.03 + Math.random() * 0.02;
    body = `${listing.display_name} reports a goal completed ahead of schedule; special dividend under review.${suffix}`;
    cash = 30;
    upd.confidence = Math.min(100, listing.confidence + 3);
  } else if (kind === 'miss') {
    frac = -(0.025 + Math.random() * 0.025);
    body = `${listing.ticker} slides after a missed session; shareholders notified.${suffix}`;
    upd.streak = 0;
    upd.quiet_days = 0;
    upd.misses = listing.misses + 1;
    upd.confidence = Math.max(0, listing.confidence - 6);
  }

  // streak: first positive action on a new day extends it
  if (kind !== 'miss') {
    if (listing.last_action_day !== day) {
      const yesterday = marketDay(new Date(Date.now() - 864e5));
      upd.streak = listing.last_action_day === yesterday ? listing.streak + 1 : 1;
      upd.confidence = Math.min(100, (upd.confidence ?? listing.confidence) + 1);
    }
    upd.last_action_day = day;
    upd.quiet_days = 0;
  }

  await applyMove(db, listing, frac, Math.round(listing.shares * 0.008));
  if (Object.keys(upd).length) await db.from('listings').update(upd).eq('id', listing.id);
  if (cash > 0) await creditCash(db, user.id, cash);
  await postEvent(db, { ticker: listing.ticker, body, move: frac });

  // guidance progress (gym sessions count toward it)
  if (kind === 'session') {
    const { data: g } = await db.from('guidance').select('*')
      .eq('listing_id', listing.id).eq('status', 'open').maybeSingle();
    if (g) {
      const done = g.done + 1;
      await db.from('guidance').update({ done }).eq('id', g.id);
      if (done >= g.target) {
        const { data: fresh } = await db.from('listings').select('*').eq('id', listing.id).single();
        await resolveGuidance(db, { ...g, done }, fresh, true);
      }
    }
  }

  // streak dividend: crossing 30 pays holders immediately
  const newStreak = upd.streak ?? listing.streak;
  if (kind !== 'miss' && newStreak === 30 && listing.streak !== 30) {
    const per = 0.04;
    const { data: holders } = await db.from('holdings').select('user_id, shares').eq('listing_id', listing.id);
    for (const h of holders || []) {
      const amt = Math.round(h.shares * per * 100) / 100;
      await creditCash(db, h.user_id, amt);
      await db.from('dividends').insert({ listing_id: listing.id, user_id: h.user_id, per_share: per, amount: amt });
    }
    await postEvent(db, { ticker: listing.ticker, kind: 'wire', body: `${listing.display_name} reaches a 30-day streak; dividend of £${per.toFixed(2)}/share declared.` });
  }

  return json({ ok: true, cash_earned: cash });
};
