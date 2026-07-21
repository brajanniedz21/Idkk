# Merit Exchange — shared version setup

This is the version where **everyone shares one exchange**: every member sees every
stock, and people can invest in their friends from any phone or laptop. It is a
single HTML file (`shared.html`) plus a free Supabase database. About 15 minutes.

You (the deployer) do this once. After that, anyone who opens your site just signs up.

---

## 1. Create the database (Supabase)

1. Go to [supabase.com](https://supabase.com), sign up, and create a new project.
   Choose a region near you and any database password (you won't need it day to day).
2. When the project finishes setting up, open **SQL Editor → New query**.
3. Open `db/schema.sql` from this repo, copy the whole file, paste it into the query
   editor, and click **Run**. This creates every table, all the game rules, security
   policies, and 21 house listings so the market feels alive on day one. You should
   see "Success. No rows returned."

## 2. Turn off email confirmation

Members log in with a ticker and password, not a real email, so confirmation must be off.

- Go to **Authentication → Providers → Email**.
- Turn **Confirm email** OFF. Save.

(Leave "Enable email provider" on. That's all you need to change.)

## 3. Get your two keys

- Go to **Project Settings → API**.
- Copy the **Project URL** (looks like `https://abcd1234.supabase.co`).
- Copy the **anon public** key (a long string). This one is safe to put in the
  webpage — the security policies from step 1 are what protect the data.
  *Do not* use the `service_role` key anywhere.

## 4. Put the keys into the file

Open `public/shared.html` in any text editor. Near the very bottom, find:

```js
window.MX_CONFIG={
  SUPABASE_URL: "PASTE_YOUR_PROJECT_URL",
  SUPABASE_ANON_KEY: "PASTE_YOUR_ANON_KEY"
};
```

Paste your Project URL and anon key between the quotes. Save.

## 5. Deploy

- Rename `public/shared.html` to `index.html`.
- Drag that single file (or a zip of it) onto [app.netlify.com/drop](https://app.netlify.com/drop).
- Done. Share the Netlify URL with your friends. Everyone who opens it is on the
  same exchange: they sign up (ticker + password), list themselves, and can trade,
  invest in each other, and bet on each other's follow-through — from any device.

## 6. (Optional) Keep the market moving 24/7

Without this, house stocks still move whenever anyone has the page open (the page
nudges the market every 30 seconds). To keep bots trading even when nobody is online:

- In Supabase: **Database → Extensions**, enable **pg_cron**.
- Then in the SQL Editor run:
  ```sql
  select cron.schedule('mx-heartbeat', '*/2 * * * *', $$select public.mx_heartbeat()$$);
  ```

---

## How sign-in works

- **New member:** tap "Create your listing", pick a ticker (e.g. `BRAJ`), a password,
  your name, company, and sector. You list at £10.00 with £500 to invest.
- **Returning:** on the sign-in screen, search the shared list of stocks, tap yours,
  and enter your password. Your ticker is your login.
- There is no password reset (there are no real emails), so keep your password safe.

## What's safe

- The browser only ever reads public market data or your own private balances, and
  every action that changes the market (logging a session, trading, staking) runs as
  a database function that checks who you are and does the maths server-side. Nobody
  can cheat by editing the page: they can't set their own price, cash, or anyone
  else's. The `anon` key in the page is public by design; Row Level Security is the
  lock.
- Actions are self-reported by design — this is an accountability game among friends,
  not surveillance. Daily caps and the social pressure do the enforcing.

## Limits

- Free Supabase pauses a project after a week of no activity; open the dashboard
  occasionally, or upgrade.
- This is a friends-scale app. It will happily hold dozens of members.
