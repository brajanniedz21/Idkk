// Scheduled: hourly. Rings the bells, rolls the daily candle once per market
// day, punishes quiet days, pays streak dividends, prunes old ticks.
import { admin, marketDay, marketHour, applyMove, postEvent, creditCash, round2 } from './_lib/core.mjs';

export default async () => {
  const db = admin();
  const today = marketDay();
  const hour = marketHour();

  const { data: kvRow } = await db.from('kv').select('value').eq('key', 'last_roll').maybeSingle();
  const lastRoll = kvRow?.value?.day;

  // ---- once per new market day: roll candles, judge yesterday, pay dividends
  if (lastRoll !== today) {
    const { data: listings } = await db.from('listings').select('*');
    const yesterday = marketDay(new Date(Date.now() - 864e5));

    for (const l of listings || []) {
      // yesterday's candle from day stats (skip listings created today)
      if (marketDay(new Date(l.listed_at)) !== today) {
        await db.from('candles_d').upsert({
          listing_id: l.id, day: yesterday,
          o: l.day_open, h: l.day_high, l: l.day_low, c: l.price, v: l.day_vol,
        }, { onConflict: 'listing_id,day' });
      }
      const upd = {
        prev_close: l.price, day_open: l.price,
        day_high: l.price, day_low: l.price, day_vol: 0,
      };

      if (!l.is_bot) {
        const quiet = l.last_action_day !== yesterday && l.last_action_day !== today;
        if (quiet && marketDay(new Date(l.listed_at)) < yesterday) {
          upd.quiet_days = l.quiet_days + 1;
          upd.streak = 0;
          upd.confidence = Math.max(0, l.confidence - 4);
          await db.from('listings').update(upd).eq('id', l.id);
          const { data: fresh } = await db.from('listings').select('*').eq('id', l.id).single();
          const frac = -(0.012 + Math.min(0.03, fresh.quiet_days * 0.006));
          await applyMove(db, fresh, frac, Math.floor(l.shares * 0.005));
          if (fresh.quiet_days === 3) {
            await postEvent(db, { ticker: l.ticker, move: frac, body: `Sell-off in ${l.ticker}: a third consecutive quiet day. Investor confidence slips.` });
          }
          continue;
        }
      } else {
        // bots keep their streaks moving
        const up = Math.random() < Number(l.bot_consistency);
        upd.streak = up ? l.streak + 1 : 0;
      }
      await db.from('listings').update(upd).eq('id', l.id);
    }

    // streak dividends at the roll: every listing at 30+ pays holders daily-ish
    const { data: payers } = await db.from('listings').select('*').gte('streak', 30);
    for (const l of payers || []) {
      const per = 0.02;
      const { data: holders } = await db.from('holdings').select('user_id, shares').eq('listing_id', l.id);
      if (!holders?.length) continue;
      for (const h of holders) {
        const amt = round2(h.shares * per);
        await creditCash(db, h.user_id, amt);
        await db.from('dividends').insert({ listing_id: l.id, user_id: h.user_id, per_share: per, amount: amt });
      }
      await postEvent(db, { ticker: l.ticker, body: `${l.display_name} extends the streak to ${l.streak} days; £${per.toFixed(2)}/share paid to holders.` });
    }

    // prune ticks older than 48 hours
    await db.from('ticks').delete().lt('ts', new Date(Date.now() - 48 * 3600e3).toISOString());

    await db.from('kv').upsert({ key: 'last_roll', value: { day: today } }, { onConflict: 'key' });
  }

  // ---- bells (this function runs hourly, so each fires once)
  const { data: bellRow } = await db.from('kv').select('value').eq('key', 'last_bell').maybeSingle();
  const lastBell = bellRow?.value?.stamp;
  if (hour === 8 && lastBell !== `open-${today}`) {
    await postEvent(db, { kind: 'bell', body: 'Opening bell. MERIT EXCHANGE is open until midnight.' });
    await db.from('kv').upsert({ key: 'last_bell', value: { stamp: `open-${today}` } }, { onConflict: 'key' });
  }
  if (hour === 0 && lastBell !== `close-${today}`) {
    await postEvent(db, { kind: 'bell', body: 'Closing bell. See you at 08:00.' });
    await db.from('kv').upsert({ key: 'last_bell', value: { stamp: `close-${today}` } }, { onConflict: 'key' });
  }

  return new Response('ok');
};

export const config = { schedule: '@hourly' };
