# MERIT EXCHANGE

A stock exchange where the listed companies are people. Consistency is the fundamentals: hit your goals and your share price climbs; miss them and the market sells you off.

This is the real, deployable app: accounts, a shared live market, trading between members, and server-authoritative prices. **Deployment guide: [SETUP.md](SETUP.md)** (Netlify + Supabase, free tiers, ~20 minutes).

```
public/               static frontend (terminal UI, charts, auth, onboarding)
netlify/functions/    game logic: IPO, actions, guidance, trading, predictions,
                      comments, reactions + two scheduled jobs (market tick, maintenance)
db/schema.sql         Postgres schema, Row Level Security, atomic trade fn, seed data
netlify.toml          build, redirects, security headers
```

A fully offline single-file demo of the concept lives at `public/demo.html` — open it in any browser, no accounts needed.

## What's in the prototype

- **Market hours** with opening bell 08:00 and closing bell 00:00; the tape freezes and the feed goes quiet when the market is closed.
- **Candlestick charts** (canvas, 1D/1M/3M/ALL) with volume, crosshair, OHLC readout, and last-price tag.
- **A live trading floor feed** printing habit events as market news: runs completed, sessions missed, all-time highs, guidance beats and cuts, dividends declared.
- **22 listed people** with ticker symbols, market caps, volumes, sparklines, and an MRX Composite index.
- **Sector indices** (Fitness, Business, Coding, Art, Education, Content Creation) with day and week moves.
- **Leaderboards**: top gainers, biggest crashes, highest market cap, most traded.
- **Company-style profiles**: CEO, fundamentals, analyst consensus, investor-confidence gauge, auto-filed monthly earnings reports with Bullish/Hold/Bearish reactions, shareholder comments.
- **Your listing (BRAJ)**: log gym sessions, deep work, goal hits, and misses; each moves your price. Issue public guidance ("5 gym sessions by Sunday") and get a surge for beating it or a sell-off for missing.
- **Shareholder pressure**: "27 shareholders are waiting on today's session."
- **Trading**: buy and sell shares in anyone with cash earned from your own consistency.
- **Dividends** paid to holders when someone's streak runs long.
- **A predictions market** with decimal odds that settles in-session.
- **IPOs**: upcoming and recent listings with prospectuses (pitch, outlook, risk factors).

Deep links: `index.html#lb`, `#pred`, `#ipo`, `#pf`, `#me`, or any ticker (`#KAI`).

Everything is simulated client-side with a seeded engine so the market is repeatable within a day but alive while you watch. `PRODUCT.md` and `DESIGN.md` document the product intent and the visual system.
