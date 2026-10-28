"""Copy the local menu log (menu_log/<week>/<servery>.json) into Supabase, then read it back.

Run once after supabase/schema.sql has been applied and .env is filled in:

    venv/bin/python scripts/backfill_supabase.py

Safe to re-run: rows are upserted on (week_key, servery).
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import servery_finder_web as app  # noqa: E402  (also loads .env)


def main():
    if not app._supabase_settings():
        sys.exit("SUPABASE_URL and SUPABASE_SECRET_KEY are not set (check .env).")

    log_dir = os.path.join(app.BASE_DIR, "menu_log")
    servery_by_file = {name.replace(' ', '-'): name for name in app.SERVERIES}
    uploaded = 0

    for week_key in sorted(os.listdir(log_dir)) if os.path.isdir(log_dir) else []:
        if not app.WEEK_KEY_RE.match(week_key):
            continue
        for filename in sorted(os.listdir(os.path.join(log_dir, week_key))):
            servery = servery_by_file.get(filename.removesuffix('.json'))
            if not servery:
                continue
            with open(os.path.join(log_dir, week_key, filename)) as f:
                record = json.load(f)
            app.supabase_upsert_menu_log(week_key, servery, record)  # raises on any HTTP error
            uploaded += 1
            print(f"uploaded {week_key} {servery}")

    weeks = app.list_logged_weeks()
    print(f"\n{uploaded} local records uploaded. Weeks now in Supabase: {', '.join(weeks) or 'none'}")


if __name__ == '__main__':
    main()
