# Deploying MERIT EXCHANGE

The site is a static frontend on Netlify, Netlify Functions for all game logic, and Supabase for accounts and the database. Total cost on free tiers: £0. Allow about 20 minutes.

## 1. Create the Supabase project

1. Go to [supabase.com](https://supabase.com), sign up, and create a new project. Pick a strong database password (you won't need it day-to-day) and a region near your users.
2. In the dashboard, open **SQL Editor → New query**, paste the entire contents of `db/schema.sql` from this repo, and run it. This creates every table, all Row Level Security policies, the trade function, and 21 seeded house listings so the market is alive from the start.
3. Open **Project Settings → API** and note three values:
   - **Project URL** (like `https://abcd1234.supabase.co`)
   - **anon public** key — safe to ship to browsers; Row Level Security is what protects data
   - **service_role** key — SECRET. Never put it in the frontend, never commit it, never share it.

## 2. Configure auth

In **Authentication → Providers → Email**: leave email + password enabled. Keep **Confirm email** ON (recommended — it stops throwaway signups). Supabase's built-in mailer is fine to start; connect your own SMTP later if you outgrow its limits.

In **Authentication → URL Configuration**, set the Site URL to your Netlify URL once you have it (step 4).

## 3. Deploy to Netlify

1. Push this repo to GitHub (already done if you're reading this there).
2. In [Netlify](https://app.netlify.com): **Add new site → Import an existing project**, pick the repo. Build settings are read from `netlify.toml` automatically.
3. Before the first deploy, add environment variables under **Site configuration → Environment variables**:

   | Key | Value | Secret? |
   |---|---|---|
   | `SUPABASE_URL` | your Project URL | no |
   | `SUPABASE_ANON_KEY` | the anon public key | no |
   | `SUPABASE_SERVICE_ROLE_KEY` | the service_role key | **yes — mark as secret** |
   | `MARKET_TZ` | `Europe/London` (or your market's timezone) | no |

4. Deploy. The build writes `public/config.js` from the two public values; the service key is only ever read inside functions.

## 4. After the first deploy

- Put your live Netlify URL into Supabase **Authentication → URL Configuration → Site URL**.
- The two scheduled functions register automatically: `market-tick` every 5 minutes (moves the market, prints the floor feed) and `maintenance` hourly (bells, daily candle roll, quiet-day penalties, dividends, guidance deadlines, settlement).
- Create your own account on the live site, list yourself, and check the floor feed prints your IPO.

## Security model (what keeps this safe)

- **Auth** is Supabase's: bcrypt-hashed passwords, JWT sessions, email confirmation, rate-limited endpoints. The app never sees or stores a password.
- **The browser can't cheat.** Row Level Security means anonymous and signed-in clients can only *read* public market data plus their own private rows (cash, holdings, trades, stakes, dividends). There are no client write policies except follow/unfollow of listings.
- **All mutations go through functions.** Logging a session, trading, staking, commenting — each is a Netlify Function that verifies the caller's JWT, validates every input, applies daily caps, and computes prices and payouts server-side. The client never supplies a price, a payout, or a cash amount.
- **Trades are atomic**: a single Postgres function locks the rows, checks cash/shares, and applies the fill, so concurrent orders can't double-spend.
- **Predictions are parimutuel**: winners split the losers' pool, so settlement can never mint currency, and you cannot bet on your own guidance.
- **Secrets stay server-side**: the service role key lives only in Netlify env vars; the build fails if it's ever mistaken for the anon key.
- **Headers**: a strict Content-Security-Policy, frame-ancestors 'none', nosniff, and referrer policy ship on every response via `netlify.toml`.

## Limits to know about

- Free-tier Supabase pauses projects after a week of inactivity; open the dashboard occasionally or upgrade.
- Netlify free tier includes 125k function invocations/month; the two schedulers use ~9.5k of that.
- Actions are self-reported by design — the game is accountability, not surveillance. Daily caps (3 sessions, 3 deep work, 2 goals) blunt spam; the social layer does the rest.
