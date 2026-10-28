# Rice Servery Finder

Search this week's menus across all Rice University serveries by dish, cuisine, dietary tag, day, or meal.

**Live site:** https://rice-servery.vercel.app

## Layout

```
servery_finder_web.py   All backend logic: scraping, caching, menu log, stats, search, PDF export, FastAPI routes
supabase/schema.sql     Supabase table + view for the menu log
scripts/                One-off scripts (backfill_supabase.py)
.env.example            Environment variables (copy to .env for local runs)
templates/index.html    The menu search page (HTML, CSS, and JS)
templates/stats.html    The Statistics page
templates/_head.html    Shared theme tokens, base styles, and the light/dark switch
templates/_header.html  Shared header and page nav
requirements.txt        Python dependencies
vercel.json             Vercel deployment config (routes everything to the Python app)
```

## How menus are extracted

1. `SERVERIES` in `servery_finder_web.py` maps each servery to its page on dining.rice.edu.
2. `_download_servery_html()` fetches the page. It sends a session cookie so Rice's CDN serves a fresh page instead of a stale cached copy with no menu items.
3. `fetch_menu_with_icons()` slices the HTML to the "View Week" block and uses regexes to pull out each day, meal, and item. `extract_icons()` reads the dietary icons (vegan, vegetarian, halal, allergens) next to each item.
4. `get_weekly_menu()` caches the result in memory for 2 hours (reset each ISO week). Rice fills in later days mid-week and blanks past days, so re-downloads keep cached days the page has since emptied. The Refresh button (`POST /api/refresh`) forces a re-download.

## How searching works

`POST /api/search` calls `find_matching_serveries()` in `servery_finder_web.py`, which walks the cached menus and applies the filters:

- Item name: `fuzzy_match()` does substring, all-words, and typo-tolerant matching.
- Cuisine: `matches_cuisine()` checks item names against keyword lists in `CUISINE_KEYWORDS`.
- Dietary: `matches_dietary()` handles include and exclude tags, combined with AND or OR.
- Day, meal, and servery filters narrow the results, which are returned sorted by day and meal.

`POST /api/export` runs the same search and renders it as a phone-sized PDF with `build_menu_pdf()`.

## Statistics page

`/statistics` charts what each servery served in a week (cuisine counts, cuisine mix, vegan/vegetarian/halal share, busiest days, most repeated dishes). The page has a time-range picker (this week, last week, last 4 weeks, all time, or any custom range of weeks). `GET /api/stats?from=2026-W40&to=2026-W44` returns the numbers from `compute_stats()`; both default to the current week. Tapping a square in the cuisine grid calls `GET /api/stats/cell?servery=seibel&cuisine=indian&from=…&to=…`, which lists every dish behind that count and the word that matched it.

Every menu download is saved to a menu log, one record per servery per ISO week, so the stats keep days that Rice has already removed from its site. Where the log lives:

- Supabase, table `menu_log`, when `SUPABASE_URL` and `SUPABASE_SECRET_KEY` are set (in `.env` locally, in Vercel's Environment Variables in production). Create the table by running `supabase/schema.sql` in the Supabase SQL Editor. `scripts/backfill_supabase.py` copies a local `menu_log/` folder into it. The `menu_items` view has one row per dish for ad-hoc SQL.
- Otherwise JSON files in `menu_log/` (or `MENU_LOG_DIR`). On Vercel that falls back to `/tmp`, which is wiped between instances.

A daily Vercel cron (`vercel.json`) calls `/api/cron/log-menus` so each day is logged before Rice blanks it. Set `CRON_SECRET` in Vercel to lock that endpoint to the cron.

## Other details

- Open/closed status uses `DINING_SCHEDULE` and `get_current_meal_and_status()` in Central Time.
- Run locally: `pip install -r requirements.txt && python servery_finder_web.py`, then open http://localhost:8000.
