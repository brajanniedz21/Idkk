import { admin, requireUser, json, readJson, postEvent } from './_lib/core.mjs';

const SECTORS = new Set(['FIT', 'BIZ', 'COD', 'ART', 'EDU', 'CRE']);
const RESERVED = new Set(['MRX', 'MERIT', 'ADMIN', 'NULL', 'MOD']);

export default async (req) => {
  if (req.method !== 'POST') return json({ error: 'POST only.' }, 405);
  const { user, errorResponse } = await requireUser(req);
  if (errorResponse) return errorResponse;

  let b;
  try { b = await readJson(req); } catch { return json({ error: 'Bad request body.' }, 400); }

  const ticker = String(b.ticker || '').toUpperCase().trim();
  const displayName = String(b.display_name || '').trim().slice(0, 40);
  const company = String(b.company || '').trim().slice(0, 60);
  const sector = String(b.sector || '');
  const pitch = String(b.pitch || '').trim().slice(0, 400);
  const outlook = String(b.outlook || '').trim().slice(0, 120);
  const risks = Array.isArray(b.risks)
    ? b.risks.map(r => String(r).trim().slice(0, 120)).filter(Boolean).slice(0, 4)
    : [];

  if (!/^[A-Z]{2,5}$/.test(ticker)) return json({ error: 'Ticker must be 2 to 5 letters A-Z.' }, 400);
  if (RESERVED.has(ticker)) return json({ error: 'That ticker is reserved.' }, 400);
  if (!displayName) return json({ error: 'Enter your name.' }, 400);
  if (!company) return json({ error: 'Enter a company name.' }, 400);
  if (!SECTORS.has(sector)) return json({ error: 'Pick a sector.' }, 400);

  const db = admin();

  const { data: mine } = await db.from('listings').select('id').eq('user_id', user.id).maybeSingle();
  if (mine) return json({ error: 'You are already listed.' }, 409);

  const { data: taken } = await db.from('listings').select('id').eq('ticker', ticker).maybeSingle();
  if (taken) return json({ error: `${ticker} is taken. Pick another ticker.` }, 409);

  const px = 10.00;
  const { data: listing, error } = await db.from('listings').insert({
    user_id: user.id, ticker, display_name: displayName, company, sector,
    pitch, outlook: outlook || 'Aggressive growth.', risks,
    shares: 2500, price: px, prev_close: px,
    day_open: px, day_high: px, day_low: px, ath: px,
  }).select().single();
  if (error) return json({ error: 'Listing failed. Try a different ticker.' }, 500);

  await db.from('accounts').upsert({ user_id: user.id }, { onConflict: 'user_id', ignoreDuplicates: true });
  await db.from('ticks').insert({ listing_id: listing.id, price: px, vol: 0 });
  await postEvent(db, {
    ticker, kind: 'sys',
    body: `IPO: ${company} (${ticker}) lists on MERIT EXCHANGE at £10.00. Sector: ${sector}.`,
  });
  return json({ ok: true, listing: { ticker: listing.ticker } });
};
