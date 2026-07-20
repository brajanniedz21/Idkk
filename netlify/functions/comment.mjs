import { admin, requireUser, json, readJson } from './_lib/core.mjs';

export default async (req) => {
  if (req.method !== 'POST') return json({ error: 'POST only.' }, 405);
  const { user, errorResponse } = await requireUser(req);
  if (errorResponse) return errorResponse;

  let b;
  try { b = await readJson(req); } catch { return json({ error: 'Bad request body.' }, 400); }
  const ticker = String(b.ticker || '').toUpperCase();
  const body = String(b.body || '').trim().slice(0, 280);
  if (!body) return json({ error: 'Write something first.' }, 400);

  const db = admin();
  const { data: listing } = await db.from('listings').select('id, user_id').eq('ticker', ticker).single();
  if (!listing) return json({ error: 'Unknown ticker.' }, 400);

  const { data: holding } = await db.from('holdings').select('shares')
    .eq('user_id', user.id).eq('listing_id', listing.id).maybeSingle();
  if (!holding?.shares) return json({ error: 'Shareholders only. Buy at least one share to comment.' }, 403);

  const { data: mine } = await db.from('listings').select('ticker').eq('user_id', user.id).single();
  const { count } = await db.from('comments')
    .select('*', { count: 'exact', head: true })
    .eq('user_id', user.id)
    .gte('created_at', new Date(Date.now() - 3600e3).toISOString());
  if ((count || 0) >= 10) return json({ error: 'Slow down. Ten comments an hour is plenty.' }, 429);

  await db.from('comments').insert({
    listing_id: listing.id, user_id: user.id,
    author: mine?.ticker || 'ANON', held: holding.shares, body,
  });
  return json({ ok: true });
};
