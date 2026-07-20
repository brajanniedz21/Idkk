// Scheduled: every 5 minutes. Moves house listings, prints wire events,
// drifts human listings gently, and settles anything past its deadline.
import { admin, marketOpen, applyMove, postEvent, settleMarket, resolveGuidance } from './_lib/core.mjs';

const gauss = () => (Math.random() + Math.random() + Math.random()) * 2 - 3;

const POS = {
  FIT: [u => `${u.display_name} completes a ${5 + Math.floor(Math.random() * 9)} km run.`,
        u => `${u.display_name} logs a 06:00 session; volume climbs.`,
        u => `${u.display_name} sets a personal record on deadlift; bonus payout under review.`],
  COD: [u => `${u.display_name} ships a feature two days ahead of schedule.`,
        u => `${u.display_name} closes out the week's sprint with zero carryover.`],
  BIZ: [u => `${u.display_name} signs a second client this month.`,
        u => `${u.display_name} clears the quarter's revenue target early.`],
  EDU: [u => `${u.display_name} logs ${2 + Math.floor(Math.random() * 3)} hours of deep study.`,
        u => `${u.display_name} passes a mock exam comfortably; buyers step in.`],
  ART: [u => `${u.display_name} finishes a commissioned piece on deadline.`],
  CRE: [u => `${u.display_name} posts day ${6 + Math.floor(Math.random() * 40)} of the daily series.`],
};
const NEG = {
  FIT: [u => `${u.display_name} misses a scheduled workout.`,
        u => `${u.display_name} skips leg day; shareholders notified.`],
  EDU: [u => `${u.display_name} abandons a planned study block.`],
  CRE: [u => `${u.display_name} breaks the posting streak; sellers in control.`],
  any: [u => `Heavy selling in ${u.ticker} after a quiet 48 hours.`,
        u => `Investor confidence in ${u.ticker} at a one-month low.`],
};

export default async () => {
  const db = admin();

  // settle expired prediction markets not tied to guidance, and expired guidance
  const nowISO = new Date().toISOString();
  const { data: dueG } = await db.from('guidance').select('*').eq('status', 'open').lt('deadline', nowISO);
  for (const g of dueG || []) {
    const { data: listing } = await db.from('listings').select('*').eq('id', g.listing_id).single();
    if (listing) await resolveGuidance(db, g, listing, g.done >= g.target);
  }
  const { data: dueM } = await db.from('pred_markets').select('*')
    .eq('status', 'open').is('guidance_id', null).lt('deadline', nowISO);
  for (const m of dueM || []) await settleMarket(db, m, Math.random() < 0.5 ? 'YES' : 'NO');

  if (!marketOpen()) return new Response('closed');

  const { data: listings } = await db.from('listings').select('*');
  if (!listings?.length) return new Response('empty');

  const bots = listings.filter(l => l.is_bot);
  const humans = listings.filter(l => !l.is_bot);

  for (const b of bots) {
    const drift = (Number(b.bot_consistency) - 0.5) * 0.0006;
    const frac = drift + Number(b.bot_vol) * 0.35 * gauss();
    await applyMove(db, b, frac, Math.floor(b.shares * 0.002 * Math.random()));
  }

  // occasionally one bot makes news
  if (bots.length && Math.random() < 0.65) {
    const b = bots[Math.floor(Math.random() * bots.length)];
    const pos = Math.random() < Number(b.bot_consistency);
    const pool = (pos ? POS[b.sector] : (NEG[b.sector] || NEG.any)) || POS.FIT;
    const text = pool[Math.floor(Math.random() * pool.length)](b);
    const frac = (0.015 + Math.random() * 0.05) * (pos ? 1 : -1);
    const px = await applyMove(db, b, frac, Math.floor(b.shares * 0.01));
    await postEvent(db, { ticker: b.ticker, body: text, move: frac });
    if (px >= Number(b.ath)) {
      await postEvent(db, { ticker: b.ticker, body: `${b.display_name} hits an all-time high of £${px.toFixed(2)}.`, move: frac });
    }
  }

  // humans drift gently toward their fundamentals between actions
  for (const h of humans) {
    const bias = ((h.confidence - 50) / 50) * 0.0008;
    const frac = bias + 0.004 * gauss();
    await applyMove(db, h, frac, Math.floor(h.shares * 0.0005 * Math.random()));
  }

  return new Response('ticked');
};

export const config = { schedule: '*/5 * * * *' };
