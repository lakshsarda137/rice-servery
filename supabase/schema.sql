-- Menu log for OwlUCanEat. Run once in the Supabase SQL Editor (safe to re-run).
--
-- One row per servery per ISO week, holding that week's menu as scraped from
-- dining.rice.edu: {"monday": {"lunch": [{"name": ..., "icons": [...]}, ...], ...}, ...}.
-- The app upserts a row every time it downloads a menu, keyed on (week_key, servery).

create table if not exists public.menu_log (
    week_key   text        not null check (week_key ~ '^\d{4}-W\d{2}$'),  -- e.g. 2026-W44
    servery    text        not null,                                       -- north, south, west, seibel, baker, south main
    fetched_at timestamptz not null,                                       -- last download from Rice
    menu       jsonb       not null,
    primary key (week_key, servery)
);

-- Only the server (secret key, which bypasses RLS) may read or write.
-- With RLS on and no policies, the public/anon key gets nothing.
alter table public.menu_log enable row level security;

-- One row per dish per meal, for querying history in the SQL Editor, e.g.
--   select servery, count(*) from menu_items where name ilike '%paneer%' group by servery;
create or replace view public.menu_items with (security_invoker = true) as
select
    m.week_key,
    m.servery,
    d.key            as day,
    meal.key         as meal,
    item ->> 'name'  as name,
    item -> 'icons'  as icons
from public.menu_log m
cross join lateral jsonb_each(m.menu) as d
cross join lateral jsonb_each(d.value) as meal
cross join lateral jsonb_array_elements(meal.value) as item;
