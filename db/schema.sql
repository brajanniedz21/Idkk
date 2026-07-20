-- MERIT EXCHANGE · Supabase schema
-- Run this whole file once in the Supabase SQL editor (Dashboard → SQL → New query).
-- Safe to re-run on a fresh project only; it does not migrate existing data.

-- ============================================================ tables

create table public.accounts (
  user_id    uuid primary key references auth.users (id) on delete cascade,
  cash       numeric(14,2) not null default 500.00 check (cash >= 0),
  created_at timestamptz not null default now()
);

create table public.listings (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid unique references auth.users (id) on delete cascade, -- null = house listing (bot)
  ticker       text not null unique check (ticker ~ '^[A-Z]{2,5}$'),
  display_name text not null check (char_length(display_name) between 1 and 40),
  company      text not null check (char_length(company) between 1 and 60),
  sector       text not null check (sector in ('FIT','BIZ','COD','ART','EDU','CRE')),
  pitch        text not null default '' check (char_length(pitch) <= 400),
  outlook      text not null default '' check (char_length(outlook) <= 120),
  risks        text[] not null default '{}',
  shares       integer not null default 2500 check (shares between 100 and 100000),
  price        numeric(12,2) not null check (price > 0),
  prev_close   numeric(12,2) not null check (prev_close > 0),
  day_open     numeric(12,2) not null,
  day_high     numeric(12,2) not null,
  day_low      numeric(12,2) not null,
  day_vol      bigint  not null default 0,
  ath          numeric(12,2) not null,
  streak       integer not null default 0 check (streak >= 0),
  misses       integer not null default 0,
  beats        integer not null default 0,
  confidence   integer not null default 50 check (confidence between 0 and 100),
  last_action_day date,
  quiet_days   integer not null default 0,
  is_bot       boolean not null default false,
  bot_consistency numeric,             -- bots only
  bot_vol      numeric,                -- bots only
  listed_at    timestamptz not null default now()
);

create table public.ticks (
  id         bigint generated always as identity primary key,
  listing_id uuid not null references public.listings (id) on delete cascade,
  ts         timestamptz not null default now(),
  price      numeric(12,2) not null,
  vol        integer not null default 0
);
create index ticks_listing_ts on public.ticks (listing_id, ts);

create table public.candles_d (
  listing_id uuid not null references public.listings (id) on delete cascade,
  day        date not null,
  o numeric(12,2) not null, h numeric(12,2) not null,
  l numeric(12,2) not null, c numeric(12,2) not null,
  v bigint not null default 0,
  primary key (listing_id, day)
);

create table public.actions (
  id         bigint generated always as identity primary key,
  listing_id uuid not null references public.listings (id) on delete cascade,
  kind       text not null check (kind in ('session','deep_work','goal','miss')),
  day        date not null,
  ts         timestamptz not null default now()
);
create index actions_listing_day on public.actions (listing_id, day);

create table public.holdings (
  user_id    uuid not null references auth.users (id) on delete cascade,
  listing_id uuid not null references public.listings (id) on delete cascade,
  shares     integer not null check (shares > 0),
  cost       numeric(14,2) not null default 0,
  primary key (user_id, listing_id)
);

create table public.trades (
  id         bigint generated always as identity primary key,
  user_id    uuid not null references auth.users (id) on delete cascade,
  listing_id uuid not null references public.listings (id) on delete cascade,
  side       text not null check (side in ('buy','sell')),
  qty        integer not null check (qty > 0),
  price      numeric(12,2) not null,
  ts         timestamptz not null default now()
);
create index trades_user_ts on public.trades (user_id, ts desc);

create table public.events (
  id     bigint generated always as identity primary key,
  ts     timestamptz not null default now(),
  ticker text,
  body   text not null check (char_length(body) <= 300),
  move   numeric,                       -- fractional move, e.g. 0.042
  kind   text not null default 'wire' check (kind in ('wire','sys','bell'))
);
create index events_ts on public.events (ts desc);

create table public.guidance (
  id         bigint generated always as identity primary key,
  listing_id uuid not null references public.listings (id) on delete cascade,
  target     integer not null check (target between 1 and 14),
  done       integer not null default 0,
  deadline   timestamptz not null,
  status     text not null default 'open' check (status in ('open','beat','miss')),
  created_at timestamptz not null default now()
);
create index guidance_listing on public.guidance (listing_id, status);

create table public.pred_markets (
  id          bigint generated always as identity primary key,
  listing_id  uuid not null references public.listings (id) on delete cascade,
  guidance_id bigint references public.guidance (id) on delete set null,
  question    text not null check (char_length(question) <= 200),
  deadline    timestamptz not null,
  status      text not null default 'open' check (status in ('open','settled','void')),
  outcome     text check (outcome in ('YES','NO')),
  created_at  timestamptz not null default now()
);

create table public.pred_stakes (
  id         bigint generated always as identity primary key,
  market_id  bigint not null references public.pred_markets (id) on delete cascade,
  user_id    uuid not null references auth.users (id) on delete cascade,
  side       text not null check (side in ('YES','NO')),
  amount     numeric(12,2) not null check (amount between 1 and 1000),
  payout     numeric(12,2),             -- written at settlement
  created_at timestamptz not null default now(),
  unique (market_id, user_id)
);

create table public.comments (
  id         bigint generated always as identity primary key,
  listing_id uuid not null references public.listings (id) on delete cascade,
  user_id    uuid not null references auth.users (id) on delete cascade,
  author     text not null,             -- commenter's ticker, snapshotted
  held       integer not null,          -- shares held at time of comment, snapshotted
  body       text not null check (char_length(body) between 1 and 280),
  created_at timestamptz not null default now()
);
create index comments_listing on public.comments (listing_id, created_at desc);

create table public.reactions (
  listing_id uuid not null references public.listings (id) on delete cascade,
  user_id    uuid not null references auth.users (id) on delete cascade,
  stance     text not null check (stance in ('bull','hold','bear')),
  primary key (listing_id, user_id)
);

create table public.follows (
  follower   uuid not null references auth.users (id) on delete cascade,
  listing_id uuid not null references public.listings (id) on delete cascade,
  primary key (follower, listing_id)
);

create table public.dividends (
  id         bigint generated always as identity primary key,
  listing_id uuid not null references public.listings (id) on delete cascade,
  user_id    uuid not null references auth.users (id) on delete cascade,
  per_share  numeric(8,2) not null,
  amount     numeric(12,2) not null,
  ts         timestamptz not null default now()
);

create table public.kv (
  key   text primary key,
  value jsonb not null
);

-- ============================================================ views
-- Aggregate views expose only counts/sums from private tables, never rows.
-- They intentionally run as owner (security definer semantics) for that reason.

create view public.holder_counts as
  select listing_id, count(*)::int as holders, coalesce(sum(shares),0)::bigint as held
  from public.holdings group by listing_id;

create view public.pred_pools as
  select market_id,
         coalesce(sum(amount) filter (where side = 'YES'),0)::numeric as yes_pool,
         coalesce(sum(amount) filter (where side = 'NO'),0)::numeric  as no_pool,
         count(*)::int as bettors
  from public.pred_stakes group by market_id;

create view public.reaction_counts as
  select listing_id,
         count(*) filter (where stance = 'bull')::int as bull,
         count(*) filter (where stance = 'hold')::int as hold,
         count(*) filter (where stance = 'bear')::int as bear
  from public.reactions group by listing_id;

grant select on public.holder_counts, public.pred_pools, public.reaction_counts to anon, authenticated;

-- ============================================================ atomic trade
-- Called only by the service role from the trade function; not exposed to clients.

create or replace function public.exec_trade(p_user uuid, p_ticker text, p_side text, p_qty int)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  l public.listings%rowtype;
  acct public.accounts%rowtype;
  h public.holdings%rowtype;
  fill numeric(12,2);
  gross numeric(14,2);
  impact numeric;
  newpx numeric(12,2);
begin
  if p_qty is null or p_qty < 1 or p_qty > 10000 then
    return jsonb_build_object('error','Quantity must be between 1 and 10,000.');
  end if;
  select * into l from listings where ticker = p_ticker for update;
  if not found then return jsonb_build_object('error','Unknown ticker.'); end if;
  select * into acct from accounts where user_id = p_user for update;
  if not found then return jsonb_build_object('error','No account.'); end if;

  fill := l.price;
  gross := round(fill * p_qty, 2);

  if p_side = 'buy' then
    if gross > acct.cash then
      return jsonb_build_object('error','Insufficient cash ('||to_char(acct.cash,'FM999999990.00')||' available).');
    end if;
    update accounts set cash = cash - gross where user_id = p_user;
    insert into holdings (user_id, listing_id, shares, cost)
      values (p_user, l.id, p_qty, gross)
      on conflict (user_id, listing_id)
      do update set shares = holdings.shares + p_qty, cost = holdings.cost + gross;
  elsif p_side = 'sell' then
    select * into h from holdings where user_id = p_user and listing_id = l.id for update;
    if not found or h.shares < p_qty then
      return jsonb_build_object('error','You hold '||coalesce(h.shares,0)||' shares.');
    end if;
    update accounts set cash = cash + gross where user_id = p_user;
    if h.shares = p_qty then
      delete from holdings where user_id = p_user and listing_id = l.id;
    else
      update holdings
        set cost = round(cost * (h.shares - p_qty)::numeric / h.shares, 2),
            shares = shares - p_qty
        where user_id = p_user and listing_id = l.id;
    end if;
  else
    return jsonb_build_object('error','Side must be buy or sell.');
  end if;

  -- small, bounded price impact from order flow
  impact := least(0.005, (p_qty::numeric / l.shares) * 0.5);
  if p_side = 'sell' then impact := -impact; end if;
  newpx := greatest(0.50, round(l.price * (1 + impact), 2));
  update listings set
    price = newpx,
    day_high = greatest(day_high, newpx),
    day_low  = least(day_low, newpx),
    day_vol  = day_vol + p_qty,
    ath      = greatest(ath, newpx)
    where id = l.id;
  insert into ticks (listing_id, price, vol) values (l.id, newpx, p_qty);
  insert into trades (user_id, listing_id, side, qty, price) values (p_user, l.id, p_side, p_qty, fill);

  return jsonb_build_object('ok', true, 'qty', p_qty, 'price', fill, 'ticker', p_ticker);
end $$;

revoke all on function public.exec_trade(uuid, text, text, int) from public, anon, authenticated;

-- ============================================================ row level security
-- Public market data is world-readable. Private rows are readable only by their
-- owner. There are no client INSERT/UPDATE policies except where noted; all
-- mutations go through Netlify functions using the service role.

alter table public.accounts     enable row level security;
alter table public.listings     enable row level security;
alter table public.ticks        enable row level security;
alter table public.candles_d    enable row level security;
alter table public.actions      enable row level security;
alter table public.holdings     enable row level security;
alter table public.trades       enable row level security;
alter table public.events       enable row level security;
alter table public.guidance     enable row level security;
alter table public.pred_markets enable row level security;
alter table public.pred_stakes  enable row level security;
alter table public.comments     enable row level security;
alter table public.reactions    enable row level security;
alter table public.follows      enable row level security;
alter table public.dividends    enable row level security;
alter table public.kv           enable row level security;   -- no policies: service role only

create policy "public read"  on public.listings     for select using (true);
create policy "public read"  on public.ticks        for select using (true);
create policy "public read"  on public.candles_d    for select using (true);
create policy "public read"  on public.actions      for select using (true);
create policy "public read"  on public.events       for select using (true);
create policy "public read"  on public.guidance     for select using (true);
create policy "public read"  on public.pred_markets for select using (true);
create policy "public read"  on public.comments     for select using (true);

create policy "own read"     on public.accounts    for select using (auth.uid() = user_id);
create policy "own read"     on public.holdings    for select using (auth.uid() = user_id);
create policy "own read"     on public.trades      for select using (auth.uid() = user_id);
create policy "own read"     on public.pred_stakes for select using (auth.uid() = user_id);
create policy "own read"     on public.dividends   for select using (auth.uid() = user_id);

create policy "own read"     on public.reactions for select using (auth.uid() = user_id);
create policy "own read"     on public.follows   for select using (auth.uid() = follower);
create policy "own write"    on public.follows   for insert with check (auth.uid() = follower);
create policy "own delete"   on public.follows   for delete using (auth.uid() = follower);

-- ============================================================ realtime
alter publication supabase_realtime add table public.events;
alter publication supabase_realtime add table public.listings;

-- ============================================================ seed: house listings
-- 21 simulated people so the floor is alive before the first human signs up.

do $$
declare
  bot record;
  d date;
  p numeric := 0; o numeric; c numeric; hi numeric; lo numeric;
  ret numeric; athv numeric;
  lid uuid;
begin
  for bot in
    select * from (values
      ('JOSH','Josh Carter','Carter Performance','FIT',0.86,0.022,2600,11.0),
      ('EMMA','Emma Kowalczyk','Kowalczyk & Co','FIT',0.42,0.030,2100,9.0),
      ('LIAM','Liam O''Shea','O''Shea Group','BIZ',0.93,0.018,3400,21.0),
      ('TOM','Tom Weaver','Weaver Systems','COD',0.71,0.020,2800,14.0),
      ('ALEX','Alexandra Reyes','Reyes Capital','BIZ',0.77,0.019,3000,17.0),
      ('SARA','Sarah Lindqvist','Lindqvist Studio','ART',0.58,0.027,1900,7.5),
      ('JACK','Jack Nowak','Nowak Athletics','FIT',0.66,0.025,2200,8.0),
      ('NOAH','Noah Adeyemi','Adeyemi Labs','COD',0.81,0.021,2500,13.0),
      ('MAYA','Maya Osei','Osei Learning','EDU',0.74,0.019,2300,10.0),
      ('FELX','Felix Braun','Braun Holdings','BIZ',0.49,0.028,2700,12.0),
      ('IVY','Ivy Chen','Chen Studio','ART',0.69,0.024,1800,6.8),
      ('DANI','Daniela Costa','Costa Media','CRE',0.62,0.031,2000,9.2),
      ('KAI','Kai Tanaka','Tanaka Systems','COD',0.88,0.017,2900,16.0),
      ('RUBY','Ruby Okafor','Okafor Capital','BIZ',0.79,0.020,3100,15.0),
      ('OWEN','Owen Gallagher','Gallagher Fitness','FIT',0.55,0.029,2000,7.0),
      ('LENA','Lena Petrova','Petrova Institute','EDU',0.83,0.018,2400,12.5),
      ('MILO','Milo Rossi','Rossi Creative','CRE',0.47,0.033,1700,5.9),
      ('ZARA','Zara Hussain','Hussain Tutoring','EDU',0.72,0.021,2100,9.6),
      ('FINN','Finn Larsen','Larsen Media','CRE',0.64,0.026,1900,8.4),
      ('ANYA','Anya Sharma','Sharma Labs','COD',0.76,0.022,2600,11.8),
      ('COLE','Cole Barrett','Barrett Athletics','FIT',0.68,0.034,1600,6.0)
    ) as t(ticker, display_name, company, sector, consistency, vol, shares, base)
  loop
    p := bot.base; athv := bot.base;
    insert into listings (ticker, display_name, company, sector, shares, price, prev_close,
                          day_open, day_high, day_low, ath, is_bot, bot_consistency, bot_vol,
                          streak, confidence, pitch, outlook)
      values (bot.ticker, bot.display_name, bot.company, bot.sector, bot.shares,
              bot.base, bot.base, bot.base, bot.base, bot.base, bot.base,
              true, bot.consistency, bot.vol,
              floor(bot.consistency * 30)::int,
              (bot.consistency * 88 + 6)::int,
              'House listing. Simulated participant, real market rules.',
              case when bot.consistency > 0.7 then 'Steady growth.' else 'Volatile.' end)
      returning id into lid;

    for i in reverse 59..1 loop
      d := current_date - i;
      ret := ((bot.consistency - 0.45) * 0.008 + bot.vol * (random()*2 - 1) * 1.6)::numeric;
      if random() < 0.09 then
        ret := ret + ((case when random() < bot.consistency then 1 else -1 end) * (0.02 + random()*0.07))::numeric;
      end if;
      o := p; c := greatest(0.5, round((p * (1 + ret))::numeric, 2));
      hi := round((greatest(o,c) * (1 + random()*bot.vol*0.8))::numeric, 2);
      lo := round((least(o,c) * (1 - random()*bot.vol*0.8))::numeric, 2);
      insert into candles_d (listing_id, day, o, h, l, c, v)
        values (lid, d, o, hi, lo, c, floor(bot.shares * (0.05 + random()*0.1))::bigint);
      if hi > athv then athv := hi; end if;
      p := c;
    end loop;

    update listings set price = p, prev_close = p, day_open = p, day_high = p, day_low = p, ath = athv
      where id = lid;
    insert into ticks (listing_id, price, vol) values (lid, p, 0);
  end loop;

  insert into events (body, kind) values ('MERIT EXCHANGE is live. Opening bell 08:00, closing bell 00:00.', 'sys');
end $$;
