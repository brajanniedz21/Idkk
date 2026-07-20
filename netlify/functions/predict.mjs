import { admin, requireUser, json, readJson, round2 } from './_lib/core.mjs';

export default async (req) => {
  if (req.method !== 'POST') return json({ error: 'POST only.' }, 405);
  const { user, errorResponse } = await requireUser(req);
  if (errorResponse) return errorResponse;

  let b;
  try { b = await readJson(req); } catch { return json({ error: 'Bad request body.' }, 400); }
  const marketId = Math.floor(Number(b.market_id));
  const side = String(b.side || '');
  const amount = round2(Number(b.amount));
  if (!marketId) return json({ error: 'Unknown market.' }, 400);
  if (side !== 'YES' && side !== 'NO') return json({ error: 'Side must be YES or NO.' }, 400);
  if (!(amount >= 1 && amount <= 1000)) return json({ error: 'Stake must be £1 to £1,000.' }, 400);

  const db = admin();
  const { data: market } = await db.from('pred_markets').select('*').eq('id', marketId).single();
  if (!market || market.status !== 'open') return json({ error: 'Market is settled.' }, 400);
  if (new Date(market.deadline) < new Date()) return json({ error: 'Market has closed.' }, 400);

  const { data: listing } = await db.from('listings').select('user_id').eq('id', market.listing_id).single();
  if (listing?.user_id === user.id) return json({ error: 'You cannot bet on your own guidance.' }, 403);

  const { data: existing } = await db.from('pred_stakes').select('id')
    .eq('market_id', marketId).eq('user_id', user.id).maybeSingle();
  if (existing) return json({ error: 'You already have a position in this market.' }, 409);

  const { data: acct } = await db.from('accounts').select('cash').eq('user_id', user.id).single();
  if (!acct || Number(acct.cash) < amount) return json({ error: 'Insufficient cash.' }, 400);

  await db.from('accounts').update({ cash: round2(Number(acct.cash) - amount) }).eq('user_id', user.id);
  const { error } = await db.from('pred_stakes').insert({ market_id: marketId, user_id: user.id, side, amount });
  if (error) {
    await db.from('accounts').update({ cash: Number(acct.cash) }).eq('user_id', user.id); // refund on race
    return json({ error: 'Stake failed. Try again.' }, 500);
  }
  return json({ ok: true });
};
