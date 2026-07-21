-- ============================================================================
-- MERIT EXCHANGE · shared database schema (client-direct model)
-- Run this whole file once in the Supabase SQL editor:
--   Dashboard -> SQL Editor -> New query -> paste -> Run.
-- Everyone who opens your deployed site shares this one database, so every
-- member sees every stock. The browser only ever SELECTs public data or calls
-- the mx_* functions below; all writes that matter run server-side here, so
-- nobody can cheat by editing the page.
-- Safe to run once on a fresh project.
-- ============================================================================

create extension if not exists pgcrypto;

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
  bot_consistency numeric,
  bot_vol      numeric,
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
  move   numeric,
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
  listing_id  uuid references public.listings (id) on delete cascade,   -- subject
  creator     uuid references auth.users (id) on delete cascade,        -- null = house
  guidance_id bigint references public.guidance (id) on delete set null,
  kind        text not null default 'habit' check (kind in ('habit','price','guidance','custom')),
  question    text not null check (char_length(question) <= 200),
  target      numeric,                       -- price markets
  p_true      numeric,                       -- habit markets (bot follow-through odds)
  yes_odds    numeric not null default 1.9,
  no_odds     numeric not null default 1.9,
  visibility  text not null default 'public' check (visibility in ('public','friends')),
  deadline    timestamptz not null,
  status      text not null default 'open' check (status in ('open','settled','void')),
  outcome     text check (outcome in ('YES','NO','VOID')),
  settled_at  timestamptz,
  created_at  timestamptz not null default now()
);
create index pred_open on public.pred_markets (status, deadline);

create table public.pred_stakes (
  id         bigint generated always as identity primary key,
  market_id  bigint not null references public.pred_markets (id) on delete cascade,
  user_id    uuid not null references auth.users (id) on delete cascade,
  side       text not null check (side in ('YES','NO')),
  amount     numeric(12,2) not null check (amount between 1 and 1000),
  payout     numeric(12,2),
  created_at timestamptz not null default now(),
  unique (market_id, user_id)
);

create table public.comments (
  id         bigint generated always as identity primary key,
  listing_id uuid not null references public.listings (id) on delete cascade,
  user_id    uuid not null references auth.users (id) on delete cascade,
  author     text not null,
  held       integer not null,
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

-- favourites double as the "friends" graph
create table public.favourites (
  user_id    uuid not null references auth.users (id) on delete cascade,
  listing_id uuid not null references public.listings (id) on delete cascade,
  primary key (user_id, listing_id)
);

create table public.dividends (
  id         bigint generated always as identity primary key,
  listing_id uuid not null references public.listings (id) on delete cascade,
  user_id    uuid not null references auth.users (id) on delete cascade,
  per_share  numeric(8,2) not null,
  amount     numeric(12,2) not null,
  ts         timestamptz not null default now()
);

create table public.kv (key text primary key, value jsonb not null);

-- ============================================================ helper views

create view public.holder_counts as
  select listing_id, count(*)::int as holders, coalesce(sum(shares),0)::bigint as held
  from public.holdings group by listing_id;

create view public.pred_pools as
  select market_id,
         coalesce(sum(amount) filter (where side='YES'),0)::numeric as yes_pool,
         coalesce(sum(amount) filter (where side='NO'),0)::numeric  as no_pool,
         count(*)::int as bettors
  from public.pred_stakes group by market_id;

create view public.reaction_counts as
  select listing_id,
         count(*) filter (where stance='bull')::int as bull,
         count(*) filter (where stance='hold')::int as hold,
         count(*) filter (where stance='bear')::int as bear
  from public.reactions group by listing_id;

-- ============================================================ internal helpers

create or replace function public._mx_uid() returns uuid
  language sql stable as $$ select auth.uid() $$;

create or replace function public._mx_round(x numeric) returns numeric
  language sql immutable as $$ select round(x, 2) $$;

create or replace function public._mx_credit(p_user uuid, amt numeric)
returns void language plpgsql security definer set search_path=public as $$
begin
  update accounts set cash = round(cash + amt, 2) where user_id = p_user;
end $$;

create or replace function public._mx_move(p_listing uuid, frac numeric, vol int default 0)
returns numeric language plpgsql security definer set search_path=public as $$
declare l listings%rowtype; px numeric;
begin
  select * into l from listings where id = p_listing for update;
  px := greatest(0.50, round(l.price * (1 + frac), 2));
  update listings set
    price = px,
    day_high = greatest(day_high, px),
    day_low  = least(day_low, px),
    day_vol  = day_vol + coalesce(vol,0),
    ath      = greatest(ath, px)
    where id = p_listing;
  insert into ticks (listing_id, price, vol) values (p_listing, px, coalesce(vol,0));
  return px;
end $$;

create or replace function public._mx_event(p_ticker text, p_body text, p_move numeric default null, p_kind text default 'wire')
returns void language plpgsql security definer set search_path=public as $$
begin
  insert into events (ticker, body, move, kind) values (p_ticker, left(p_body,300), p_move, p_kind);
end $$;

-- settle a prediction market: winners split the losers' pool (parimutuel);
-- one-sided or void markets refund every stake.
create or replace function public._mx_settle(p_market bigint, p_outcome text)
returns void language plpgsql security definer set search_path=public as $$
declare
  m pred_markets%rowtype; s pred_stakes%rowtype;
  yes_pool numeric; no_pool numeric; win_pool numeric; lose_pool numeric; pay numeric;
begin
  select * into m from pred_markets where id = p_market for update;
  if not found or m.status <> 'open' then return; end if;

  select coalesce(sum(amount) filter (where side='YES'),0),
         coalesce(sum(amount) filter (where side='NO'),0)
    into yes_pool, no_pool from pred_stakes where market_id = p_market;

  if p_outcome = 'VOID' or yes_pool = 0 or no_pool = 0 then
    for s in select * from pred_stakes where market_id = p_market loop
      perform _mx_credit(s.user_id, s.amount);
      update pred_stakes set payout = s.amount where id = s.id;
    end loop;
    update pred_markets set status='void', outcome='VOID', settled_at=now() where id = p_market;
    return;
  end if;

  win_pool  := case when p_outcome='YES' then yes_pool else no_pool end;
  lose_pool := case when p_outcome='YES' then no_pool  else yes_pool end;
  for s in select * from pred_stakes where market_id = p_market loop
    if s.side = p_outcome then
      pay := round(s.amount + (s.amount / win_pool) * lose_pool, 2);
      perform _mx_credit(s.user_id, pay);
    else pay := 0; end if;
    update pred_stakes set payout = pay where id = s.id;
  end loop;
  update pred_markets set status='settled', outcome=p_outcome, settled_at=now() where id = p_market;
end $$;

create or replace function public._mx_resolve_guidance(p_g bigint, p_beat boolean)
returns void language plpgsql security definer set search_path=public as $$
declare g guidance%rowtype; l listings%rowtype; frac numeric; mk bigint;
begin
  select * into g from guidance where id = p_g for update;
  if not found or g.status <> 'open' then return; end if;
  select * into l from listings where id = g.listing_id;
  frac := case when p_beat then 0.06 + random()*0.03 else -(0.07 + random()*0.03) end;
  perform _mx_move(l.id, frac, round(l.shares*0.02)::int);
  update guidance set status = case when p_beat then 'beat' else 'miss' end where id = p_g;
  if p_beat then
    update listings set beats = beats+1, confidence = least(100,confidence+6) where id = l.id;
    perform _mx_credit(l.user_id, 40);
    perform _mx_event(l.ticker, l.display_name||' beats guidance ('||g.target||' sessions); shares gap up.', frac);
  else
    update listings set misses = misses+1, confidence = greatest(0,confidence-8) where id = l.id;
    perform _mx_event(l.ticker, l.display_name||' misses guidance ('||g.done||' of '||g.target||' sessions); the market punishes it.', frac);
  end if;
  for mk in select id from pred_markets where guidance_id = p_g and status='open' loop
    perform _mx_settle(mk, case when p_beat then 'YES' else 'NO' end);
  end loop;
end $$;

-- ============================================================ player RPCs

-- List yourself. Called right after auth signUp; ticker must match the one
-- baked into your login. One listing per account.
create or replace function public.mx_ipo(
  p_ticker text, p_name text, p_company text, p_sector text,
  p_pitch text, p_outlook text, p_risks text[])
returns jsonb language plpgsql security definer set search_path=public as $$
declare uid uuid := auth.uid(); lid uuid; px numeric := 10.00;
begin
  if uid is null then return jsonb_build_object('error','Not signed in.'); end if;
  p_ticker := upper(p_ticker);
  if p_ticker !~ '^[A-Z]{2,5}$' then return jsonb_build_object('error','Ticker must be 2 to 5 letters.'); end if;
  if p_sector not in ('FIT','BIZ','COD','ART','EDU','CRE') then return jsonb_build_object('error','Pick a sector.'); end if;
  if coalesce(trim(p_name),'')='' or coalesce(trim(p_company),'')='' then return jsonb_build_object('error','Enter your name and company.'); end if;
  if exists (select 1 from listings where user_id = uid) then return jsonb_build_object('error','You are already listed.'); end if;
  if exists (select 1 from listings where ticker = p_ticker) then return jsonb_build_object('error',p_ticker||' is taken.'); end if;

  insert into listings (user_id, ticker, display_name, company, sector, pitch, outlook, risks,
                        shares, price, prev_close, day_open, day_high, day_low, ath)
    values (uid, p_ticker, left(p_name,40), left(p_company,60), p_sector,
            left(coalesce(p_pitch,''),400), coalesce(nullif(left(coalesce(p_outlook,''),120),''),'Aggressive growth.'),
            coalesce(p_risks,'{}'), 2500, px, px, px, px, px, px)
    returning id into lid;
  insert into accounts (user_id) values (uid) on conflict (user_id) do nothing;
  insert into ticks (listing_id, price, vol) values (lid, px, 0);
  perform _mx_event(p_ticker, p_company||' ('||p_ticker||') lists on MERIT EXCHANGE at £10.00.', null, 'sys');
  return jsonb_build_object('ok', true, 'ticker', p_ticker);
end $$;

-- Log a real-life action. Moves your own price; caps per day.
create or replace function public.mx_action(p_kind text)
returns jsonb language plpgsql security definer set search_path=public as $$
declare
  uid uuid := auth.uid(); l listings%rowtype; today date := current_date;
  n int; frac numeric; cash numeric := 0; body text; new_streak int; g guidance%rowtype;
  cap int; per numeric; h record;
begin
  if uid is null then return jsonb_build_object('error','Not signed in.'); end if;
  if p_kind not in ('session','deep_work','goal','miss') then return jsonb_build_object('error','Unknown action.'); end if;
  select * into l from listings where user_id = uid for update;
  if not found then return jsonb_build_object('error','You are not listed yet.'); end if;

  cap := case p_kind when 'session' then 3 when 'deep_work' then 3 when 'goal' then 2 else 3 end;
  select count(*) into n from actions where listing_id=l.id and day=today and kind=p_kind;
  if n >= cap then return jsonb_build_object('error','Daily limit reached for that action. Resets at the opening bell.'); end if;

  insert into actions (listing_id, kind, day) values (l.id, p_kind, today);

  if p_kind = 'session' then
    frac := (0.018 + random()*0.014) * power(0.45, n);  cash := case when n=0 then 12 else 4 end;
    body := l.display_name||' logs a gym session; the desk takes notice.';
  elsif p_kind = 'deep_work' then
    frac := (0.008 + random()*0.008) * power(0.55, n);  cash := case when n=0 then 6 else 2 end;
    body := l.display_name||' logs two hours of focused work.';
  elsif p_kind = 'goal' then
    frac := 0.03 + random()*0.02;  cash := 30;
    body := l.display_name||' reports a goal completed ahead of schedule.';
  else
    frac := -(0.025 + random()*0.025);
    body := l.ticker||' slides after a missed session; shareholders notified.';
  end if;

  -- streak bookkeeping
  if p_kind = 'miss' then
    update listings set streak=0, quiet_days=0, misses=misses+1, confidence=greatest(0,confidence-6) where id=l.id;
    new_streak := 0;
  else
    if l.last_action_day is distinct from today then
      new_streak := case when l.last_action_day = today - 1 then l.streak + 1 else 1 end;
    else new_streak := l.streak; end if;
    update listings set streak=new_streak, quiet_days=0, last_action_day=today,
      confidence=least(100, confidence + case when l.last_action_day is distinct from today then 1 else 0 end
                              + case when p_kind='goal' then 3 else 0 end)
      where id=l.id;
  end if;

  perform _mx_move(l.id, frac, round(l.shares*0.008)::int);
  if cash > 0 then perform _mx_credit(uid, cash); end if;
  perform _mx_event(l.ticker, body, frac);

  -- guidance progress
  if p_kind = 'session' then
    select * into g from guidance where listing_id=l.id and status='open' limit 1;
    if found then
      update guidance set done = done+1 where id=g.id;
      if g.done + 1 >= g.target then perform _mx_resolve_guidance(g.id, true); end if;
    end if;
  end if;

  -- 30-day streak dividend to holders
  if p_kind <> 'miss' and new_streak = 30 and l.streak <> 30 then
    per := 0.04;
    for h in select user_id, shares from holdings where listing_id=l.id loop
      perform _mx_credit(h.user_id, round(h.shares*per,2));
      insert into dividends (listing_id, user_id, per_share, amount) values (l.id, h.user_id, per, round(h.shares*per,2));
    end loop;
    perform _mx_event(l.ticker, l.display_name||' reaches a 30-day streak; £0.04/share dividend declared.');
  end if;

  return jsonb_build_object('ok', true, 'cash_earned', cash);
end $$;

create or replace function public.mx_guidance(p_target int)
returns jsonb language plpgsql security definer set search_path=public as $$
declare uid uuid := auth.uid(); l listings%rowtype; dl timestamptz; gid bigint;
begin
  if uid is null then return jsonb_build_object('error','Not signed in.'); end if;
  if p_target < 1 or p_target > 14 then return jsonb_build_object('error','Guidance must be 1 to 14 sessions.'); end if;
  select * into l from listings where user_id=uid;
  if not found then return jsonb_build_object('error','You are not listed yet.'); end if;
  if exists (select 1 from guidance where listing_id=l.id and status='open') then
    return jsonb_build_object('error','You already have active guidance.'); end if;
  -- next Sunday 23:59 UTC
  dl := (date_trunc('day', now()) + ((7 - extract(dow from now())::int) % 7) * interval '1 day' + interval '23 hours 59 minutes');
  if dl <= now() then dl := dl + interval '7 days'; end if;
  insert into guidance (listing_id, target, deadline) values (l.id, p_target, dl) returning id into gid;
  insert into pred_markets (listing_id, guidance_id, kind, question, visibility, deadline, yes_odds, no_odds)
    values (l.id, gid, 'guidance',
            'Will '||l.display_name||' complete '||p_target||' gym sessions by Sunday?',
            'public', dl,
            round(0.95/greatest(0.1,least(0.9, l.confidence/100.0)),2),
            round(0.95/greatest(0.1,least(0.9, 1-l.confidence/100.0)),2));
  perform _mx_event(l.ticker, l.ticker||' issues guidance: '||p_target||' gym sessions by Sunday close.');
  return jsonb_build_object('ok', true);
end $$;

-- Buy/sell any listing except your own. Atomic; bounded price impact.
create or replace function public.mx_trade(p_ticker text, p_side text, p_qty int)
returns jsonb language plpgsql security definer set search_path=public as $$
declare
  uid uuid := auth.uid(); l listings%rowtype; acct accounts%rowtype; h holdings%rowtype;
  fill numeric; gross numeric; impact numeric; newpx numeric; pos_sh int; pos_cost numeric;
begin
  if uid is null then return jsonb_build_object('error','Not signed in.'); end if;
  if p_qty is null or p_qty < 1 or p_qty > 10000 then return jsonb_build_object('error','Quantity must be 1 to 10,000.'); end if;
  if p_side not in ('buy','sell') then return jsonb_build_object('error','Side must be buy or sell.'); end if;
  select * into l from listings where ticker = upper(p_ticker) for update;
  if not found then return jsonb_build_object('error','Unknown ticker.'); end if;
  if l.user_id = uid then return jsonb_build_object('error','Insiders cannot trade their own listing.'); end if;
  select * into acct from accounts where user_id = uid for update;
  if not found then return jsonb_build_object('error','No account.'); end if;

  fill := l.price; gross := round(fill * p_qty, 2);
  if p_side = 'buy' then
    if gross > acct.cash then return jsonb_build_object('error','Insufficient cash (£'||to_char(acct.cash,'FM999999990.00')||' available).'); end if;
    update accounts set cash = cash - gross where user_id = uid;
    insert into holdings (user_id, listing_id, shares, cost) values (uid, l.id, p_qty, gross)
      on conflict (user_id, listing_id) do update set shares = holdings.shares + p_qty, cost = holdings.cost + gross;
  else
    select * into h from holdings where user_id=uid and listing_id=l.id for update;
    if not found or h.shares < p_qty then return jsonb_build_object('error','You hold '||coalesce(h.shares,0)||' shares.'); end if;
    update accounts set cash = cash + gross where user_id = uid;
    if h.shares = p_qty then delete from holdings where user_id=uid and listing_id=l.id;
    else update holdings set cost = round(cost*(h.shares-p_qty)::numeric/h.shares,2), shares = shares - p_qty
         where user_id=uid and listing_id=l.id; end if;
  end if;

  impact := least(0.005, (p_qty::numeric / l.shares) * 0.5) * case when p_side='sell' then -1 else 1 end;
  newpx := _mx_move(l.id, impact, p_qty);

  insert into trades (user_id, listing_id, side, qty, price) values (uid, l.id, p_side, p_qty, fill);
  select shares, cost into pos_sh, pos_cost from holdings where user_id=uid and listing_id=l.id;
  return jsonb_build_object('ok', true, 'qty', p_qty, 'price', fill, 'gross', gross,
    'cash', (select cash from accounts where user_id=uid),
    'pos_shares', coalesce(pos_sh,0), 'pos_cost', coalesce(pos_cost,0), 'ticker', l.ticker);
end $$;

create or replace function public.mx_predict(p_market bigint, p_side text, p_amount numeric)
returns jsonb language plpgsql security definer set search_path=public as $$
declare uid uuid := auth.uid(); m pred_markets%rowtype; acct accounts%rowtype;
begin
  if uid is null then return jsonb_build_object('error','Not signed in.'); end if;
  if p_side not in ('YES','NO') then return jsonb_build_object('error','Side must be YES or NO.'); end if;
  p_amount := round(p_amount,2);
  if p_amount < 1 or p_amount > 1000 then return jsonb_build_object('error','Stake must be £1 to £1,000.'); end if;
  select * into m from pred_markets where id = p_market for update;
  if not found or m.status <> 'open' then return jsonb_build_object('error','Market is settled.'); end if;
  if now() > m.deadline then return jsonb_build_object('error','Market has closed.'); end if;
  if m.creator = uid then return jsonb_build_object('error','You cannot stake a market you settle.'); end if;
  if exists (select 1 from listings where id=m.listing_id and user_id=uid) then
    return jsonb_build_object('error','You cannot bet on your own guidance.'); end if;
  if exists (select 1 from pred_stakes where market_id=p_market and user_id=uid) then
    return jsonb_build_object('error','You already have a position in this market.'); end if;
  select * into acct from accounts where user_id=uid for update;
  if acct.cash < p_amount then return jsonb_build_object('error','Insufficient cash.'); end if;
  update accounts set cash = cash - p_amount where user_id=uid;
  insert into pred_stakes (market_id, user_id, side, amount) values (p_market, uid, p_side, p_amount);
  return jsonb_build_object('ok', true);
end $$;

create or replace function public.mx_create_market(p_question text, p_when text, p_visibility text)
returns jsonb language plpgsql security definer set search_path=public as $$
declare uid uuid := auth.uid(); l listings%rowtype; dl timestamptz;
begin
  if uid is null then return jsonb_build_object('error','Not signed in.'); end if;
  select * into l from listings where user_id=uid;
  if not found then return jsonb_build_object('error','You are not listed yet.'); end if;
  p_question := trim(p_question);
  if char_length(p_question) < 8 then return jsonb_build_object('error','Write the market first (8+ characters).'); end if;
  if (select count(*) from pred_markets where creator=uid and status='open') >= 3 then
    return jsonb_build_object('error','Three open personal markets is plenty. Settle one first.'); end if;
  if p_when = 'tonight' then dl := date_trunc('day',now()) + interval '23 hours 59 minutes';
    if dl <= now() then dl := dl + interval '1 day'; end if;
  elsif p_when = 'friday' then
    dl := date_trunc('day',now()) + (((5 - extract(dow from now())::int) + 7) % 7) * interval '1 day' + interval '23 hours 59 minutes';
    if dl <= now() then dl := dl + interval '7 days'; end if;
  else
    dl := date_trunc('day',now()) + (((0 - extract(dow from now())::int) + 7) % 7) * interval '1 day' + interval '23 hours 59 minutes';
    if dl <= now() then dl := dl + interval '7 days'; end if;
  end if;
  insert into pred_markets (listing_id, creator, kind, question, visibility, deadline)
    values (l.id, uid, 'custom', left(p_question,200),
            case when p_visibility='friends' then 'friends' else 'public' end, dl);
  if p_visibility <> 'friends' then
    perform _mx_event(l.ticker, l.ticker||' opens a market: "'||left(p_question,120)||'"');
  end if;
  return jsonb_build_object('ok', true);
end $$;

create or replace function public.mx_settle_market(p_market bigint, p_outcome text)
returns jsonb language plpgsql security definer set search_path=public as $$
declare uid uuid := auth.uid(); m pred_markets%rowtype;
begin
  if uid is null then return jsonb_build_object('error','Not signed in.'); end if;
  if p_outcome not in ('YES','NO','VOID') then return jsonb_build_object('error','Bad outcome.'); end if;
  select * into m from pred_markets where id=p_market;
  if not found or m.creator <> uid then return jsonb_build_object('error','Not your market.'); end if;
  if m.status <> 'open' then return jsonb_build_object('error','Already settled.'); end if;
  perform _mx_settle(p_market, p_outcome);
  return jsonb_build_object('ok', true);
end $$;

create or replace function public.mx_comment(p_ticker text, p_body text)
returns jsonb language plpgsql security definer set search_path=public as $$
declare uid uuid := auth.uid(); l listings%rowtype; me listings%rowtype; sh int; recent int;
begin
  if uid is null then return jsonb_build_object('error','Not signed in.'); end if;
  p_body := trim(p_body);
  if char_length(p_body) < 1 then return jsonb_build_object('error','Write something first.'); end if;
  select * into l from listings where ticker=upper(p_ticker);
  if not found then return jsonb_build_object('error','Unknown ticker.'); end if;
  select shares into sh from holdings where user_id=uid and listing_id=l.id;
  if coalesce(sh,0) < 1 then return jsonb_build_object('error','Shareholders only. Buy at least one share to comment.'); end if;
  select count(*) into recent from comments where user_id=uid and created_at > now() - interval '1 hour';
  if recent >= 10 then return jsonb_build_object('error','Slow down. Ten comments an hour is plenty.'); end if;
  select * into me from listings where user_id=uid;
  insert into comments (listing_id, user_id, author, held, body)
    values (l.id, uid, coalesce(me.ticker,'ANON'), sh, left(p_body,280));
  return jsonb_build_object('ok', true);
end $$;

create or replace function public.mx_react(p_ticker text, p_stance text)
returns jsonb language plpgsql security definer set search_path=public as $$
declare uid uuid := auth.uid(); l listings%rowtype;
begin
  if uid is null then return jsonb_build_object('error','Not signed in.'); end if;
  select * into l from listings where ticker=upper(p_ticker);
  if not found then return jsonb_build_object('error','Unknown ticker.'); end if;
  if p_stance = 'clear' then delete from reactions where listing_id=l.id and user_id=uid;
  elsif p_stance in ('bull','hold','bear') then
    insert into reactions (listing_id, user_id, stance) values (l.id, uid, p_stance)
      on conflict (listing_id, user_id) do update set stance = excluded.stance;
  else return jsonb_build_object('error','Bad stance.'); end if;
  return jsonb_build_object('ok', true);
end $$;

create or replace function public.mx_set_fav(p_ticker text, p_on boolean)
returns jsonb language plpgsql security definer set search_path=public as $$
declare uid uuid := auth.uid(); l listings%rowtype;
begin
  if uid is null then return jsonb_build_object('error','Not signed in.'); end if;
  select * into l from listings where ticker=upper(p_ticker);
  if not found then return jsonb_build_object('error','Unknown ticker.'); end if;
  if p_on then insert into favourites (user_id, listing_id) values (uid, l.id) on conflict do nothing;
  else delete from favourites where user_id=uid and listing_id=l.id; end if;
  return jsonb_build_object('ok', true);
end $$;

-- Markets visible to the caller: public ones, own guidance, plus friends-only
-- markets whose creator has favourited the caller's listing.
create or replace function public.mx_open_markets()
returns setof pred_markets language sql stable security definer set search_path=public as $$
  select m.* from pred_markets m
  where m.status='open'
    and (
      m.visibility='public'
      or m.creator = auth.uid()
      or exists (
        select 1 from favourites f
        join listings me on me.user_id = auth.uid()
        where f.user_id = m.creator and f.listing_id = me.id
      )
    )
  order by (m.kind='custom') desc, m.deadline asc;
$$;

-- ============================================================ heartbeat
-- Moves house listings, prints the floor feed, drifts nothing passively for
-- members, rolls the daily candle once per day, applies quiet-day penalties,
-- pays streak dividends, rings the bells, and settles expired markets.
-- Called by the browser every ~30s (guarded by a lock so simultaneous callers
-- do one unit of work) and optionally by pg_cron for 24/7 life.

create or replace function public.mx_heartbeat()
returns jsonb language plpgsql security definer set search_path=public as $$
declare
  last_tick timestamptz; last_roll date; today date := current_date;
  hr int := extract(hour from now())::int;
  b listings%rowtype; l listings%rowtype; g record; m record;
  did_roll boolean := false; frac numeric; px numeric; up boolean;
  yesterday date := current_date - 1; per numeric; h record; q text; k int;
begin
  -- serialize: bail if another caller ticked within 20s
  insert into kv(key,value) values ('last_tick', to_jsonb(now())) on conflict (key) do nothing;
  select (value #>> '{}')::timestamptz into last_tick from kv where key='last_tick' for update;
  if last_tick is not null and now() - last_tick < interval '20 seconds'
     and exists (select 1 from ticks limit 1) then
    -- still settle time-based things cheaply, but skip bot churn
    null;
  else
    update kv set value = to_jsonb(now()) where key='last_tick';

    -- settle expired guidance + markets
    for g in select * from guidance where status='open' and deadline < now() loop
      perform _mx_resolve_guidance(g.id, g.done >= g.target);
    end loop;
    for m in select * from pred_markets where status='open' and guidance_id is null
             and creator is null and deadline < now() loop
      -- house markets settle objectively for price, else on the subject's odds
      if m.kind='price' then
        select price into px from listings where id=m.listing_id;
        perform _mx_settle(m.id, case when px > m.target then 'YES' else 'NO' end);
      else
        perform _mx_settle(m.id, case when random() < coalesce(m.p_true,0.5) then 'YES' else 'NO' end);
      end if;
    end loop;
    -- custom markets abandoned 3 days past deadline: void + refund
    for m in select * from pred_markets where status='open' and creator is not null
             and deadline < now() - interval '3 days' loop
      perform _mx_settle(m.id, 'VOID');
    end loop;

    -- bells (once each per day)
    if hr >= 8 then
      if (select value #>> '{}' from kv where key='bell_open') is distinct from today::text then
        perform _mx_event(null, 'Opening bell. MERIT EXCHANGE is open until midnight.', null, 'bell');
        insert into kv(key,value) values ('bell_open', to_jsonb(today::text))
          on conflict (key) do update set value = excluded.value;
      end if;
    end if;

    -- daily roll (once per day): candle, quiet-day penalty, dividends
    select (value #>> '{}')::date into last_roll from kv where key='last_roll';
    if last_roll is distinct from today then
      did_roll := true;
      for l in select * from listings loop
        if l.listed_at::date < today then
          insert into candles_d (listing_id, day, o,h,l,c,v)
            values (l.id, yesterday, l.day_open, l.day_high, l.day_low, l.price, l.day_vol)
            on conflict (listing_id, day) do update set o=excluded.o,h=excluded.h,l=excluded.l,c=excluded.c,v=excluded.v;
        end if;
        if not l.is_bot and l.listed_at::date < yesterday
           and l.last_action_day is distinct from yesterday and l.last_action_day is distinct from today then
          update listings set quiet_days=quiet_days+1, streak=0, confidence=greatest(0,confidence-4) where id=l.id;
          select * into l from listings where id=l.id;
          frac := -(0.012 + least(0.03, l.quiet_days*0.006));
          perform _mx_move(l.id, frac, round(l.shares*0.005)::int);
          if l.quiet_days = 3 then
            perform _mx_event(l.ticker, 'Sell-off in '||l.ticker||': a third quiet day. Confidence slips.', frac);
          end if;
        elsif l.is_bot then
          update listings set streak = case when random() < coalesce(l.bot_consistency,.6) then streak+1 else 0 end where id=l.id;
        end if;
        update listings set prev_close=price, day_open=price, day_high=price, day_low=price, day_vol=0 where id=l.id;
      end loop;
      -- streak dividends (>=30)
      for l in select * from listings where streak >= 30 loop
        per := 0.02;
        for h in select user_id, shares from holdings where listing_id=l.id loop
          perform _mx_credit(h.user_id, round(h.shares*per,2));
          insert into dividends (listing_id, user_id, per_share, amount) values (l.id, h.user_id, per, round(h.shares*per,2));
        end loop;
        perform _mx_event(l.ticker, l.display_name||' extends the streak to '||l.streak||' days; £0.02/share paid to holders.');
      end loop;
      delete from ticks where ts < now() - interval '2 days';
      insert into kv(key,value) values ('last_roll', to_jsonb(today::text))
        on conflict (key) do update set value = excluded.value;
    end if;

    -- market open: churn bots + occasional wire event
    if hr >= 8 then
      for b in select * from listings where is_bot loop
        frac := (coalesce(b.bot_consistency,.6)-0.5)*0.0006 + coalesce(b.bot_vol,.02)*0.35*(random()*2-1);
        perform _mx_move(b.id, frac, floor(b.shares*0.002*random())::int);
      end loop;
      if random() < 0.7 then
        select * into b from listings where is_bot order by random() limit 1;
        up := random() < coalesce(b.bot_consistency,.6);
        frac := (0.015 + random()*0.05) * case when up then 1 else -1 end;
        px := _mx_move(b.id, frac, floor(b.shares*0.01)::int);
        if up then
          q := (array[
            b.display_name||' completes a '||(5+floor(random()*9))::int||' km run.',
            b.display_name||' ships a feature ahead of schedule.',
            b.display_name||' logs a 06:00 session; volume climbs.',
            b.display_name||' clears the week''s target early.'])[1+floor(random()*4)];
        else
          q := (array[
            b.display_name||' misses a scheduled workout.',
            b.display_name||' breaks a streak; sellers step in.',
            'Heavy selling in '||b.ticker||' after a quiet 48 hours.',
            'Investor confidence in '||b.ticker||' at a one-month low.'])[1+floor(random()*4)];
        end if;
        perform _mx_event(b.ticker, q, frac);
        if px >= b.ath then perform _mx_event(b.ticker, b.display_name||' hits an all-time high of £'||to_char(px,'FM999990.00')||'.', frac); end if;
      end if;
      -- keep ~6 open house markets
      select count(*) into k from pred_markets where status='open' and creator is null and guidance_id is null;
      while k < 6 loop
        select * into b from listings where is_bot order by random() limit 1;
        if random() < 0.5 then
          frac := (case when random()<.5 then 1 else -1 end)*(0.002+random()*0.006);
          insert into pred_markets (listing_id, kind, question, target, yes_odds, no_odds, deadline)
            values (b.id, 'price', 'Will '||b.ticker||' trade above £'||to_char(round(b.price*(1+frac),2),'FM999990.00')||' at '||to_char(now()+interval '8 min','HH24:MI')||'?',
                    round(b.price*(1+frac),2), 1.9, 1.9, now() + (4+random()*10)*interval '1 min');
        else
          insert into pred_markets (listing_id, kind, question, p_true, yes_odds, no_odds, deadline)
            values (b.id, 'habit', 'Will '||b.display_name||' log the next session in time?',
                    coalesce(b.bot_consistency,.6),
                    round(0.95/greatest(0.1,coalesce(b.bot_consistency,.6)),2),
                    round(0.95/greatest(0.1,1-coalesce(b.bot_consistency,.6)),2),
                    now() + (4+random()*10)*interval '1 min');
        end if;
        k := k + 1;
      end loop;
    end if;
  end if;

  -- closing bell
  if hr = 0 and (select value #>> '{}' from kv where key='bell_close') is distinct from today::text then
    perform _mx_event(null, 'Closing bell. See you at 08:00.', null, 'bell');
    insert into kv(key,value) values ('bell_close', to_jsonb(today::text))
      on conflict (key) do update set value = excluded.value;
  end if;

  return jsonb_build_object('ok', true);
end $$;

-- ============================================================ grants + RLS

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
alter table public.favourites   enable row level security;
alter table public.dividends    enable row level security;
alter table public.kv           enable row level security;

-- public (anon + authenticated) read for the shared market surface
create policy pub_read on public.listings     for select using (true);
create policy pub_read on public.ticks        for select using (true);
create policy pub_read on public.candles_d    for select using (true);
create policy pub_read on public.actions      for select using (true);
create policy pub_read on public.events       for select using (true);
create policy pub_read on public.guidance     for select using (true);
create policy pub_read on public.pred_markets for select using (true);
create policy pub_read on public.comments     for select using (true);

-- own private rows
create policy own_read on public.accounts    for select using (auth.uid() = user_id);
create policy own_read on public.holdings    for select using (auth.uid() = user_id);
create policy own_read on public.trades      for select using (auth.uid() = user_id);
create policy own_read on public.pred_stakes for select using (auth.uid() = user_id);
create policy own_read on public.dividends   for select using (auth.uid() = user_id);
create policy own_read on public.reactions   for select using (auth.uid() = user_id);
create policy own_read on public.favourites  for select using (auth.uid() = user_id);

grant select on public.holder_counts, public.pred_pools, public.reaction_counts to anon, authenticated;
grant execute on function
  public.mx_ipo(text,text,text,text,text,text,text[]),
  public.mx_action(text), public.mx_guidance(int),
  public.mx_trade(text,text,int), public.mx_predict(bigint,text,numeric),
  public.mx_create_market(text,text,text), public.mx_settle_market(bigint,text),
  public.mx_comment(text,text), public.mx_react(text,text), public.mx_set_fav(text,boolean),
  public.mx_open_markets(), public.mx_heartbeat()
  to authenticated;
grant execute on function public.mx_heartbeat(), public.mx_open_markets() to anon;

-- realtime
alter publication supabase_realtime add table public.events;
alter publication supabase_realtime add table public.listings;

-- ============================================================ seed house listings
do $$
declare bot record; d date; p numeric; o numeric; c numeric; hi numeric; lo numeric;
  ret numeric; athv numeric; lid uuid;
begin
  for bot in select * from (values
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
  ) as t(ticker,display_name,company,sector,consistency,vol,shares,base)
  loop
    p := bot.base; athv := bot.base;
    insert into listings (ticker,display_name,company,sector,shares,price,prev_close,
                          day_open,day_high,day_low,ath,is_bot,bot_consistency,bot_vol,streak,confidence,pitch,outlook)
      values (bot.ticker,bot.display_name,bot.company,bot.sector,bot.shares,
              bot.base,bot.base,bot.base,bot.base,bot.base,bot.base,true,bot.consistency,bot.vol,
              floor(bot.consistency*30)::int,(bot.consistency*88+6)::int,
              'House listing. Simulated participant, real market rules.',
              case when bot.consistency>0.7 then 'Steady growth.' else 'Volatile.' end)
      returning id into lid;
    for i in reverse 59..1 loop
      d := current_date - i;
      ret := ((bot.consistency-0.45)*0.008 + bot.vol*(random()*2-1)*1.6)::numeric;
      if random()<0.09 then ret := ret + ((case when random()<bot.consistency then 1 else -1 end)*(0.02+random()*0.07))::numeric; end if;
      o := p; c := greatest(0.5, round((p*(1+ret))::numeric,2));
      hi := round((greatest(o,c)*(1+random()*bot.vol*0.8))::numeric,2);
      lo := round((least(o,c)*(1-random()*bot.vol*0.8))::numeric,2);
      insert into candles_d (listing_id,day,o,h,l,c,v)
        values (lid,d,o,hi,lo,c,floor(bot.shares*(0.05+random()*0.1))::bigint);
      if hi>athv then athv:=hi; end if; p:=c;
    end loop;
    update listings set price=p,prev_close=p,day_open=p,day_high=p,day_low=p,ath=athv where id=lid;
    insert into ticks (listing_id,price,vol) values (lid,p,0);
  end loop;
  insert into events (body,kind) values ('MERIT EXCHANGE is live. Opening bell 08:00, closing bell 00:00.','sys');
end $$;

-- ============================================================ optional: 24/7 heartbeat via pg_cron
-- Without this, the market still moves whenever anyone has the page open.
-- To keep bots trading around the clock, enable pg_cron in the Supabase
-- dashboard (Database -> Extensions -> pg_cron), then run:
--   select cron.schedule('mx-heartbeat', '*/2 * * * *', $$select public.mx_heartbeat()$$);
