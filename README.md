# Rice Servery Finder

Search this week's menus across all Rice University serveries by dish, cuisine, dietary tag, day, or meal.

**Live site:** https://rice-servery.vercel.app

## Layout

```
servery_finder_web.py   All backend logic: scraping, caching, search, PDF export, FastAPI routes
templates/index.html    The single-page frontend (HTML, CSS, and JS)
requirements.txt        Python dependencies
vercel.json             Vercel deployment config (routes everything to the Python app)
```

## How menus are extracted

1. `SERVERIES` in `servery_finder_web.py` maps each servery to its page on dining.rice.edu.
2. `_download_servery_html()` fetches the page. It sends a session cookie so Rice's CDN serves a fresh page instead of a stale cached copy with no menu items.
3. `fetch_menu_with_icons()` slices the HTML to the "View Week" block and uses regexes to pull out each day, meal, and item. `extract_icons()` reads the dietary icons (vegan, vegetarian, halal, allergens) next to each item.
4. `get_weekly_menu()` caches the result in memory per ISO week, so Rice is hit once per servery per week. The Refresh button (`POST /api/refresh`) forces a re-download.

## How searching works

`POST /api/search` calls `find_matching_serveries()` in `servery_finder_web.py`, which walks the cached menus and applies the filters:

- Item name: `fuzzy_match()` does substring, all-words, and typo-tolerant matching.
- Cuisine: `matches_cuisine()` checks item names against keyword lists in `CUISINE_KEYWORDS`.
- Dietary: `matches_dietary()` handles include and exclude tags, combined with AND or OR.
- Day, meal, and servery filters narrow the results, which are returned sorted by day and meal.

`POST /api/export` runs the same search and renders it as a phone-sized PDF with `build_menu_pdf()`.

## Other details

- Open/closed status uses `DINING_SCHEDULE` and `get_current_meal_and_status()` in Central Time.
- Run locally: `pip install -r requirements.txt && python servery_finder_web.py`, then open http://localhost:8000.
