import { admin, requireUser, json, readJson } from './_lib/core.mjs';

export default async (req) => {
  if (req.method !== 'POST') return json({ error: 'POST only.' }, 405);
  const { user, errorResponse } = await requireUser(req);
  if (errorResponse) return errorResponse;

  let b;
  try { b = await readJson(req); } catch { return json({ error: 'Bad request body.' }, 400); }
  const ticker = String(b.ticker || '').toUpperCase();
  const side = String(b.side || '');
  const qty = Math.floor(Number(b.qty));
  if (!/^[A-Z]{2,5}$/.test(ticker)) return json({ error: 'Unknown ticker.' }, 400);
  if (side !== 'buy' && side !== 'sell') return json({ error: 'Side must be buy or sell.' }, 400);
  if (!(qty >= 1 && qty <= 10000)) return json({ error: 'Quantity must be between 1 and 10,000.' }, 400);

  const db = admin();
  const { data, error } = await db.rpc('exec_trade', {
    p_user: user.id, p_ticker: ticker, p_side: side, p_qty: qty,
  });
  if (error) return json({ error: 'Order failed. Try again.' }, 500);
  if (data?.error) return json({ error: data.error }, 400);
  return json(data);
};
