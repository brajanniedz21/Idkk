import { admin, requireUser, json, readJson } from './_lib/core.mjs';

export default async (req) => {
  if (req.method !== 'POST') return json({ error: 'POST only.' }, 405);
  const { user, errorResponse } = await requireUser(req);
  if (errorResponse) return errorResponse;

  let b;
  try { b = await readJson(req); } catch { return json({ error: 'Bad request body.' }, 400); }
  const ticker = String(b.ticker || '').toUpperCase();
  const stance = String(b.stance || '');
  if (!['bull', 'hold', 'bear', 'clear'].includes(stance)) return json({ error: 'Bad stance.' }, 400);

  const db = admin();
  const { data: listing } = await db.from('listings').select('id').eq('ticker', ticker).single();
  if (!listing) return json({ error: 'Unknown ticker.' }, 400);

  if (stance === 'clear') {
    await db.from('reactions').delete().eq('listing_id', listing.id).eq('user_id', user.id);
  } else {
    await db.from('reactions').upsert(
      { listing_id: listing.id, user_id: user.id, stance },
      { onConflict: 'listing_id,user_id' },
    );
  }
  return json({ ok: true });
};
