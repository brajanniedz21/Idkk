import { admin, requireUser, json, readJson, postEvent, endOfWeekISO } from './_lib/core.mjs';

export default async (req) => {
  if (req.method !== 'POST') return json({ error: 'POST only.' }, 405);
  const { user, errorResponse } = await requireUser(req);
  if (errorResponse) return errorResponse;

  let b;
  try { b = await readJson(req); } catch { return json({ error: 'Bad request body.' }, 400); }
  const target = Math.floor(Number(b.target));
  if (!(target >= 1 && target <= 14)) return json({ error: 'Guidance must be 1 to 14 sessions.' }, 400);

  const db = admin();
  const { data: listing } = await db.from('listings').select('*').eq('user_id', user.id).single();
  if (!listing) return json({ error: 'You are not listed yet.' }, 400);

  const { data: open } = await db.from('guidance').select('id')
    .eq('listing_id', listing.id).eq('status', 'open').maybeSingle();
  if (open) return json({ error: 'You already have active guidance. Beat it or miss it first.' }, 409);

  const deadline = endOfWeekISO();
  const { data: g, error } = await db.from('guidance')
    .insert({ listing_id: listing.id, target, deadline }).select().single();
  if (error) return json({ error: 'Could not publish guidance.' }, 500);

  await postEvent(db, {
    ticker: listing.ticker, kind: 'wire',
    body: `${listing.ticker} issues guidance: ${target} gym sessions by Sunday close.`,
  });
  await db.from('pred_markets').insert({
    listing_id: listing.id, guidance_id: g.id,
    question: `Will ${listing.display_name} complete ${target} gym sessions by Sunday?`,
    deadline,
  });
  return json({ ok: true });
};
