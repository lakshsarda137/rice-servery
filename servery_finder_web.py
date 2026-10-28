"""
Enhanced Servery Finder with Icon Extraction and Web Interface
"""

import urllib.parse
import urllib.request
import urllib.error
import json
import re
import secrets
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from datetime import date, datetime, timedelta, timezone, time as dt_time
from typing import Optional, Dict, Any, Tuple
from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import pytz
from io import BytesIO
from xml.sax.saxutils import escape as xml_escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import inch
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether)

app = FastAPI()
import os

# Resolve relative to this file: on Vercel the process cwd is not the project dir.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_env_file(path: str) -> None:
    """Read KEY=value lines from a local .env (Vercel injects env vars itself). Real env vars win."""
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env_file(os.path.join(BASE_DIR, '.env'))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# Central Time Zone (Rice University is in Houston, TX)
CST = pytz.timezone('America/Chicago')

# Dietary icons mapping
# Maps lowercase tooltip values from Rice's website to our standardized labels
DIETARY_ICONS = {
    'vegan': 'Vegan',
    'vegetarian': 'Vegetarian',
    'gluten': 'Gluten',
    'soy': 'Soy',
    'dairy': 'Dairy',
    'milk': 'Dairy',  # Rice uses "Milk" in tooltips
    'egg': 'Eggs',
    'eggs': 'Eggs',
    'fish': 'Fish',
    'shellfish': 'Shellfish',
    'peanut': 'Peanuts',
    'peanuts': 'Peanuts',
    'tree nut': 'Tree Nuts',
    'tree nuts': 'Tree Nuts',
    'halal': 'Halal',
    'sesame': 'Sesame'
}

# Cuisine keywords
CUISINE_KEYWORDS = {
    # Includes the misspellings Rice actually posts (e.g. "Butter Panner", "Chicken Briyani").
    'indian': ['curry', 'masala', 'tikka', 'biryani', 'briyani', 'biriyani', 'naan', 'dal', 'daal',
               'dhal', 'chana', 'chole', 'samosa', 'tandoori', 'tandoor', 'roti', 'paratha', 'ghee',
               'cumin', 'turmeric', 'basmati rice', 'palak', 'saag', 'paneer', 'panner', 'korma',
               'vindaloo', 'makhani', 'raita', 'papadum', 'pappadum', 'papad', 'poppadom', 'aloo',
               'matar', 'gobi', 'bhindi', 'rajma', 'jeera', 'pulao', 'pakora', 'bhaji', 'kofta',
               'keema', 'jalfrezi', 'rogan josh', 'chutney', 'dosa', 'idli', 'sambar', 'chaat',
               'kheer', 'gulab jamun', 'lassi', 'tadka', 'dhaba'],
    'chinese': ['kung pao', 'szechuan', 'szechwan', 'general tso', 'orange chicken', 'lo mein',
                'chow mein', 'fried rice', 'dumpling', 'wonton', 'peking', 'canton', 'cantonese', 'hunan',
                'sweet and sour', 'mapo', 'char siu', 'bao', 'dim sum', 'hot pot', 'shrimp'],
    'asian': ['wok', 'stir fry', 'bulgogi', 'pad thai', 'sushi', 'ramen', 'kimchi', 
              'gochujang', 'hoisin', 'miso', 'teriyaki', 'jasmine rice', 'short grain rice',
              'spring roll', 'dumpling', 'pho', 'szechuan', 'kung pao', 'shrimp'],
    'japanese': ['sushi', 'ramen', 'teriyaki', 'miso', 'tempura', 'udon', 'soba', 'yakitori',
                 'tonkatsu', 'katsu', 'wasabi', 'ginger', 'sake', 'tamari', 'dashi', 'shrimp'],
    'thai': ['pad thai', 'tom yum', 'tom kha', 'green curry', 'red curry', 'massaman', 'panang',
             'larb', 'som tam', 'mango sticky rice', 'coconut milk', 'lemongrass', 'galangal',
             'fish sauce', 'prik khing', 'prik king', 'shrimp'],
    'mexican': ['taco', 'fajita', 'burrito', 'quesadilla', 'enchilada', 'salsa', 'guacamole',
                'cilantro', 'chipotle', 'pinto beans', 'refried beans', 'tortilla', 'tostada',
                'pupusa', 'picadillo', 'elote'],
    'italian': ['pasta', 'pizza', 'lasagna', 'risotto', 'marinara', 'alfredo', 'parmesan',
                'mozzarella', 'bolognese', 'carbonara', 'pesto', 'focaccia'],
    'french': ['ratatouille', 'coq au vin', 'bouillabaisse', 'cassoulet', 'quiche', 'crepe',
               'croissant', 'brie', 'camembert', 'provencal', 'bourguignon', 'confit',
               'bechamel', 'hollandaise', 'duck confit', 'escargot'],
    'korean': ['kimchi', 'bulgogi', 'bibimbap', 'korean bbq', 'gochujang', 'soju', 'galbi',
               'japchae', 'tteokbokki', 'banchan', 'korean fried chicken', 'samgyeopsal'],
    'vietnamese': ['pho', 'banh mi', 'spring roll', 'vermicelli', 'nuoc cham', 'lemongrass',
                   'hoisin', 'fish sauce', 'bun', 'goi', 'com tam'],
    'greek': ['gyro', 'tzatziki', 'feta', 'olive', 'spanakopita', 'moussaka', 'souvlaki',
              'dolmades', 'baklava', 'greek salad', 'hummus', 'pita'],
    'mediterranean': ['mezze', 'hummus', 'pita', 'garbanzo', 'tzatziki', 'olive', 'feta',
                      'tabbouleh', 'falafel', 'tahini', 'moussaka', 'spanakorizo', 'shrimp'],
    'american': ['burger', 'hamburger', 'fries', 'mac and cheese', 'meatloaf', 'shepherd\'s pie',
                 'mashed potatoes', 'gravy', 'biscuit', 'cornbread']
}

# Items naming another cuisine are not counted for this one even if a keyword hits
# (e.g. "Japanese Carrot & Potato Curry" or a "Thai Curry" bowl is not Indian).
CUISINE_EXCLUDE_KEYWORDS = {
    'indian': ['thai', 'japanese', 'chinese', 'korean', 'jamaican', 'caribbean', 'katsu'],
}


def _keyword_regex(words):
    # Whole-word match with optional plural, so "roti" doesn't hit "Rotini" or "dal" hit "Medallions".
    return re.compile(r'\b(?:' + '|'.join(re.escape(w) for w in words) + r')(?:e?s)?\b', re.IGNORECASE)


CUISINE_PATTERNS = {key: _keyword_regex(words + [key]) for key, words in CUISINE_KEYWORDS.items()}
CUISINE_EXCLUDE_PATTERNS = {key: _keyword_regex(words) for key, words in CUISINE_EXCLUDE_KEYWORDS.items()}

# Servery key -> path on https://dining.rice.edu/. Each page holds both the
# "View Day" and "View Week" tabs; we parse the "View Week" block (#block-weeklylunch).
SERVERIES = {
    'north': 'north-servery',
    'south': 'south-servery',
    'west': 'west-servery',
    'seibel': 'seibel-servery',
    'baker': 'baker-college-kitchen',
    'south main': 'south-main-servery',
}

# Dining schedule (CST) - Fall/Spring hours as posted at https://dining.rice.edu/#dining-hours (checked 2026-08-24)
# Format: {servery: {day_of_week: [(meal_type, start_time, end_time), ...]}}
# day_of_week: 0=Monday, 6=Sunday
# Meal types: breakfast, snack_period, lunch, munch, dinner, late_night
DINING_SCHEDULE = {
    'seibel': {
        # Mon-Fri: B 7:30-10, Snack 10-11, L 11:30-2; Mon-Thu: D 5:30-8, Late Night 9-11; Fri dinner closed; Sat closed; Sun: B 8-11, L 11:30-2, Munch 3-5, D 5:30-8:30
        0: [('breakfast', dt_time(7, 30), dt_time(10, 0)), ('snack_period', dt_time(10, 0), dt_time(11, 0)), ('lunch', dt_time(11, 30), dt_time(14, 0)), ('dinner', dt_time(17, 30), dt_time(20, 0)), ('late_night', dt_time(21, 0), dt_time(23, 0))],  # Mon
        1: [('breakfast', dt_time(7, 30), dt_time(10, 0)), ('snack_period', dt_time(10, 0), dt_time(11, 0)), ('lunch', dt_time(11, 30), dt_time(14, 0)), ('dinner', dt_time(17, 30), dt_time(20, 0)), ('late_night', dt_time(21, 0), dt_time(23, 0))],  # Tue
        2: [('breakfast', dt_time(7, 30), dt_time(10, 0)), ('snack_period', dt_time(10, 0), dt_time(11, 0)), ('lunch', dt_time(11, 30), dt_time(14, 0)), ('dinner', dt_time(17, 30), dt_time(20, 0)), ('late_night', dt_time(21, 0), dt_time(23, 0))],  # Wed
        3: [('breakfast', dt_time(7, 30), dt_time(10, 0)), ('snack_period', dt_time(10, 0), dt_time(11, 0)), ('lunch', dt_time(11, 30), dt_time(14, 0)), ('dinner', dt_time(17, 30), dt_time(20, 0)), ('late_night', dt_time(21, 0), dt_time(23, 0))],  # Thu
        4: [('breakfast', dt_time(7, 30), dt_time(10, 0)), ('snack_period', dt_time(10, 0), dt_time(11, 0)), ('lunch', dt_time(11, 30), dt_time(14, 0))],  # Fri
        5: [],  # Sat (closed)
        6: [('breakfast', dt_time(8, 0), dt_time(11, 0)), ('lunch', dt_time(11, 30), dt_time(14, 0)), ('munch', dt_time(15, 0), dt_time(17, 0)), ('dinner', dt_time(17, 30), dt_time(20, 30))],  # Sun
    },
    'north': {
        # Mon-Fri: B 7:30-10, Snack 10-11, L 11:30-2, Snack 4-5, D 5:30-9; Sat: B 8-11, L 11:30-2, Munch 3-5, D 5:30-8:30; Sun closed
        0: [('breakfast', dt_time(7, 30), dt_time(10, 0)), ('snack_period', dt_time(10, 0), dt_time(11, 0)), ('lunch', dt_time(11, 30), dt_time(14, 0)), ('snack_period', dt_time(16, 0), dt_time(17, 0)), ('dinner', dt_time(17, 30), dt_time(21, 0))],  # Mon
        1: [('breakfast', dt_time(7, 30), dt_time(10, 0)), ('snack_period', dt_time(10, 0), dt_time(11, 0)), ('lunch', dt_time(11, 30), dt_time(14, 0)), ('snack_period', dt_time(16, 0), dt_time(17, 0)), ('dinner', dt_time(17, 30), dt_time(21, 0))],  # Tue
        2: [('breakfast', dt_time(7, 30), dt_time(10, 0)), ('snack_period', dt_time(10, 0), dt_time(11, 0)), ('lunch', dt_time(11, 30), dt_time(14, 0)), ('snack_period', dt_time(16, 0), dt_time(17, 0)), ('dinner', dt_time(17, 30), dt_time(21, 0))],  # Wed
        3: [('breakfast', dt_time(7, 30), dt_time(10, 0)), ('snack_period', dt_time(10, 0), dt_time(11, 0)), ('lunch', dt_time(11, 30), dt_time(14, 0)), ('snack_period', dt_time(16, 0), dt_time(17, 0)), ('dinner', dt_time(17, 30), dt_time(21, 0))],  # Thu
        4: [('breakfast', dt_time(7, 30), dt_time(10, 0)), ('snack_period', dt_time(10, 0), dt_time(11, 0)), ('lunch', dt_time(11, 30), dt_time(14, 0)), ('snack_period', dt_time(16, 0), dt_time(17, 0)), ('dinner', dt_time(17, 30), dt_time(21, 0))],  # Fri
        5: [('breakfast', dt_time(8, 0), dt_time(11, 0)), ('lunch', dt_time(11, 30), dt_time(14, 0)), ('munch', dt_time(15, 0), dt_time(17, 0)), ('dinner', dt_time(17, 30), dt_time(20, 30))],  # Sat
        6: [],  # Sun (closed)
    },
    'south': {
        # Mon-Fri: B 7:30-10:30, L 11:30-1:30, Munch 2-4, D 5-9; Sat: B 8-11, L 11:30-2, Munch 3-5, D 5:30-8:30; Sun closed
        0: [('breakfast', dt_time(7, 30), dt_time(10, 30)), ('lunch', dt_time(11, 30), dt_time(13, 30)), ('munch', dt_time(14, 0), dt_time(16, 0)), ('dinner', dt_time(17, 0), dt_time(21, 0))],  # Mon
        1: [('breakfast', dt_time(7, 30), dt_time(10, 30)), ('lunch', dt_time(11, 30), dt_time(13, 30)), ('munch', dt_time(14, 0), dt_time(16, 0)), ('dinner', dt_time(17, 0), dt_time(21, 0))],  # Tue
        2: [('breakfast', dt_time(7, 30), dt_time(10, 30)), ('lunch', dt_time(11, 30), dt_time(13, 30)), ('munch', dt_time(14, 0), dt_time(16, 0)), ('dinner', dt_time(17, 0), dt_time(21, 0))],  # Wed
        3: [('breakfast', dt_time(7, 30), dt_time(10, 30)), ('lunch', dt_time(11, 30), dt_time(13, 30)), ('munch', dt_time(14, 0), dt_time(16, 0)), ('dinner', dt_time(17, 0), dt_time(21, 0))],  # Thu
        4: [('breakfast', dt_time(7, 30), dt_time(10, 30)), ('lunch', dt_time(11, 30), dt_time(13, 30)), ('munch', dt_time(14, 0), dt_time(16, 0)), ('dinner', dt_time(17, 0), dt_time(21, 0))],  # Fri
        5: [('breakfast', dt_time(8, 0), dt_time(11, 0)), ('lunch', dt_time(11, 30), dt_time(14, 0)), ('munch', dt_time(15, 0), dt_time(17, 0)), ('dinner', dt_time(17, 30), dt_time(20, 30))],  # Sat
        6: [],  # Sun (closed)
    },
    'west': {
        # Mon-Fri: B 7:30-10:30, L 11:30-1:30, Munch 2-4; Mon-Thu: D 5-8, Late Night 9-11; Fri dinner closed; Sat: B 8-11, L 11:30-2, Munch 3-5, D 5:30-8:30; Sun closed
        0: [('breakfast', dt_time(7, 30), dt_time(10, 30)), ('lunch', dt_time(11, 30), dt_time(13, 30)), ('munch', dt_time(14, 0), dt_time(16, 0)), ('dinner', dt_time(17, 0), dt_time(20, 0)), ('late_night', dt_time(21, 0), dt_time(23, 0))],  # Mon
        1: [('breakfast', dt_time(7, 30), dt_time(10, 30)), ('lunch', dt_time(11, 30), dt_time(13, 30)), ('munch', dt_time(14, 0), dt_time(16, 0)), ('dinner', dt_time(17, 0), dt_time(20, 0)), ('late_night', dt_time(21, 0), dt_time(23, 0))],  # Tue
        2: [('breakfast', dt_time(7, 30), dt_time(10, 30)), ('lunch', dt_time(11, 30), dt_time(13, 30)), ('munch', dt_time(14, 0), dt_time(16, 0)), ('dinner', dt_time(17, 0), dt_time(20, 0)), ('late_night', dt_time(21, 0), dt_time(23, 0))],  # Wed
        3: [('breakfast', dt_time(7, 30), dt_time(10, 30)), ('lunch', dt_time(11, 30), dt_time(13, 30)), ('munch', dt_time(14, 0), dt_time(16, 0)), ('dinner', dt_time(17, 0), dt_time(20, 0)), ('late_night', dt_time(21, 0), dt_time(23, 0))],  # Thu
        4: [('breakfast', dt_time(7, 30), dt_time(10, 30)), ('lunch', dt_time(11, 30), dt_time(13, 30)), ('munch', dt_time(14, 0), dt_time(16, 0))],  # Fri
        5: [('breakfast', dt_time(8, 0), dt_time(11, 0)), ('lunch', dt_time(11, 30), dt_time(14, 0)), ('munch', dt_time(15, 0), dt_time(17, 0)), ('dinner', dt_time(17, 30), dt_time(20, 30))],  # Sat
        6: [],  # Sun (closed)
    },
    'south main': {
        # Mon-Fri: B 7:30-10:30, L 11:30-1:30, Snack 4-5, D 5:30-9; Sat-Sun: B 8-11, L 11:30-2, Munch 3-5, D 5:30-8:30
        0: [('breakfast', dt_time(7, 30), dt_time(10, 30)), ('lunch', dt_time(11, 30), dt_time(13, 30)), ('snack_period', dt_time(16, 0), dt_time(17, 0)), ('dinner', dt_time(17, 30), dt_time(21, 0))],  # Mon
        1: [('breakfast', dt_time(7, 30), dt_time(10, 30)), ('lunch', dt_time(11, 30), dt_time(13, 30)), ('snack_period', dt_time(16, 0), dt_time(17, 0)), ('dinner', dt_time(17, 30), dt_time(21, 0))],  # Tue
        2: [('breakfast', dt_time(7, 30), dt_time(10, 30)), ('lunch', dt_time(11, 30), dt_time(13, 30)), ('snack_period', dt_time(16, 0), dt_time(17, 0)), ('dinner', dt_time(17, 30), dt_time(21, 0))],  # Wed
        3: [('breakfast', dt_time(7, 30), dt_time(10, 30)), ('lunch', dt_time(11, 30), dt_time(13, 30)), ('snack_period', dt_time(16, 0), dt_time(17, 0)), ('dinner', dt_time(17, 30), dt_time(21, 0))],  # Thu
        4: [('breakfast', dt_time(7, 30), dt_time(10, 30)), ('lunch', dt_time(11, 30), dt_time(13, 30)), ('snack_period', dt_time(16, 0), dt_time(17, 0)), ('dinner', dt_time(17, 30), dt_time(21, 0))],  # Fri
        5: [('breakfast', dt_time(8, 0), dt_time(11, 0)), ('lunch', dt_time(11, 30), dt_time(14, 0)), ('munch', dt_time(15, 0), dt_time(17, 0)), ('dinner', dt_time(17, 30), dt_time(20, 30))],  # Sat
        6: [('breakfast', dt_time(8, 0), dt_time(11, 0)), ('lunch', dt_time(11, 30), dt_time(14, 0)), ('munch', dt_time(15, 0), dt_time(17, 0)), ('dinner', dt_time(17, 30), dt_time(20, 30))],  # Sun
    },
    'baker': {
        # Mon-Fri: B 7:30-10:30, L 11:30-2, D 5-8; Sat-Sun closed
        0: [('breakfast', dt_time(7, 30), dt_time(10, 30)), ('lunch', dt_time(11, 30), dt_time(14, 0)), ('dinner', dt_time(17, 0), dt_time(20, 0))],  # Mon
        1: [('breakfast', dt_time(7, 30), dt_time(10, 30)), ('lunch', dt_time(11, 30), dt_time(14, 0)), ('dinner', dt_time(17, 0), dt_time(20, 0))],  # Tue
        2: [('breakfast', dt_time(7, 30), dt_time(10, 30)), ('lunch', dt_time(11, 30), dt_time(14, 0)), ('dinner', dt_time(17, 0), dt_time(20, 0))],  # Wed
        3: [('breakfast', dt_time(7, 30), dt_time(10, 30)), ('lunch', dt_time(11, 30), dt_time(14, 0)), ('dinner', dt_time(17, 0), dt_time(20, 0))],  # Thu
        4: [('breakfast', dt_time(7, 30), dt_time(10, 30)), ('lunch', dt_time(11, 30), dt_time(14, 0)), ('dinner', dt_time(17, 0), dt_time(20, 0))],  # Fri
        5: [],  # Sat (closed)
        6: [],  # Sun (closed)
    },
}


def get_current_meal_and_status(servery_name: str, day_name: str) -> Tuple[Optional[str], bool]:
    """
    Returns (current_meal_type, is_open) for a servery on a given day.
    current_meal_type can be 'breakfast', 'lunch', 'dinner', or None if closed.
    """
    # Get current time in CST
    now_cst = datetime.now(CST)
    current_time = now_cst.time()
    current_weekday = now_cst.weekday()  # 0=Monday, 6=Sunday
    
    # Map day name to weekday number
    day_map = {
        'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
        'friday': 4, 'saturday': 5, 'sunday': 6
    }
    
    day_num = day_map.get(day_name.lower())
    if day_num is None:
        return None, False
    
    # Check if we're looking at today
    if day_num != current_weekday:
        return None, False
    
    # Get schedule for this servery and day
    schedule = DINING_SCHEDULE.get(servery_name.lower(), {})
    day_schedule = schedule.get(day_num, [])
    
    if not day_schedule:
        return None, False
    
    # Check which meal period we're in
    for meal_type, start_time, end_time in day_schedule:
        # Normalize late_night to dinner for matching
        meal_to_check = 'dinner' if meal_type == 'late_night' else meal_type
        if start_time <= current_time <= end_time:
            return meal_to_check, True
    
    return None, False

# In-memory weekly cache:
# {
#   "week_key": "2025-W49",
#   "menus": {
#       "north": { ... },  # structure returned by fetch_menu_with_icons
#       ...
#   }
# }
MENU_TTL_SECONDS = 2 * 60 * 60  # re-download a servery after this long

MENU_CACHE: Dict[str, Any] = {
    "week_key": None,
    "fetched_at": {},   # servery -> ISO timestamp (CST) of the last successful fetch
    "menus": {}
}


# Persistent menu log: one record {"fetched_at", "menu"} per (ISO week, servery).
# It backs the Statistics page and survives serverless cold starts, which matters
# because Rice blanks out past days - once a day is gone from their page, the log
# is the only copy. Stored in Supabase (table menu_log, see supabase/schema.sql)
# when SUPABASE_URL and SUPABASE_SECRET_KEY are set, otherwise as JSON files
# (MENU_LOG_DIR; /tmp on Vercel, which is wiped between instances).
MENU_LOG_DIR = os.environ.get("MENU_LOG_DIR") or (
    "/tmp/menu_log" if os.environ.get("VERCEL") else os.path.join(BASE_DIR, "menu_log"))
WEEK_KEY_RE = re.compile(r'^\d{4}-W\d{2}$')


def _supabase_settings() -> Optional[Tuple[str, str]]:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SECRET_KEY")
    if not (url and key):
        return None
    # Accept the dashboard's "RESTful endpoint" form (…supabase.co/rest/v1/) as well as the plain project URL
    return re.sub(r'/rest/v1/?$', '', url.rstrip('/')), key


def _supabase(method: str, params: Dict[str, str], body=None, prefer: Optional[str] = None):
    """Call Supabase's REST API (PostgREST) on the menu_log table. Raises on HTTP errors."""
    url, key = _supabase_settings()
    headers = {'apikey': key, 'Content-Type': 'application/json'}
    # Legacy service_role keys are JWTs and also go in Authorization; new sb_secret_ keys only use apikey
    if key.startswith('eyJ'):
        headers['Authorization'] = f'Bearer {key}'
    if prefer:
        headers['Prefer'] = prefer
    query = urllib.parse.urlencode(params, quote_via=urllib.parse.quote, safe=',.')
    req = urllib.request.Request(
        f"{url}/rest/v1/menu_log?{query}", method=method, headers=headers,
        data=json.dumps(body).encode() if body is not None else None)
    with urllib.request.urlopen(req, timeout=8) as response:
        raw = response.read().decode()
        return json.loads(raw) if raw else None


def supabase_upsert_menu_log(week_key: str, servery_name: str, record: Dict[str, Any]) -> None:
    _supabase('POST', {'on_conflict': 'week_key,servery'},
              body={'week_key': week_key, 'servery': servery_name,
                    'fetched_at': record['fetched_at'], 'menu': record['menu']},
              prefer='resolution=merge-duplicates,return=minimal')


def _log_file(week_key: str, servery_name: str) -> str:
    return os.path.join(MENU_LOG_DIR, week_key, servery_name.replace(' ', '-') + '.json')


def load_menu_log(week_key: str, servery_name: str) -> Optional[Dict[str, Any]]:
    try:
        if _supabase_settings():
            rows = _supabase('GET', {'select': 'fetched_at,menu',
                                     'week_key': f'eq.{week_key}', 'servery': f'eq.{servery_name}'})
            return rows[0] if rows else None
        with open(_log_file(week_key, servery_name)) as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except Exception as e:
        print(f"Menu log read failed for {week_key}/{servery_name}: {e}")
        return None


def save_menu_log(week_key: str, servery_name: str, record: Dict[str, Any]) -> None:
    try:
        if _supabase_settings():
            supabase_upsert_menu_log(week_key, servery_name, record)
            return
        path = _log_file(week_key, servery_name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            json.dump(record, f)
    except Exception as e:
        print(f"Menu log write failed for {week_key}/{servery_name}: {e}")


def load_menu_logs(from_key: str, to_key: str) -> Dict[Tuple[str, str], Dict[str, Any]]:
    """Every logged menu with from_key <= week <= to_key, as {(week_key, servery): menu}.

    One Supabase query for the whole range (week keys sort as text), so long
    ranges don't cost a request per servery per week.
    """
    menus = {}
    try:
        if _supabase_settings():
            rows = _supabase('GET', {'select': 'week_key,servery,menu',
                                     'and': f'(week_key.gte.{from_key},week_key.lte.{to_key})'}) or []
            for row in rows:
                menus[(row['week_key'], row['servery'])] = row['menu'] or {}
            return menus
        if not os.path.isdir(MENU_LOG_DIR):
            return menus
        for week_key in os.listdir(MENU_LOG_DIR):
            if not (WEEK_KEY_RE.match(week_key) and from_key <= week_key <= to_key):
                continue
            for servery_name in SERVERIES:
                logged = load_menu_log(week_key, servery_name)
                if logged:
                    menus[(week_key, servery_name)] = logged.get("menu") or {}
    except Exception as e:
        print(f"Menu log range read failed for {from_key}..{to_key}: {e}")
    return menus


def list_logged_weeks():
    try:
        if _supabase_settings():
            weeks = {row['week_key'] for row in _supabase('GET', {'select': 'week_key'}) or []}
        else:
            weeks = os.listdir(MENU_LOG_DIR) if os.path.isdir(MENU_LOG_DIR) else []
    except Exception as e:
        print(f"Menu log listing failed: {e}")
        weeks = []
    return sorted(w for w in weeks if WEEK_KEY_RE.match(w))


def extract_icons(icons_html):
    """Extract dietary icons from HTML
    
    Rice's website uses tooltips with data-content attributes.
    Tooltip values found: Vegan, Vegetarian, Gluten, Soy, Milk, Eggs, Fish, Shellfish, Halal, Sesame
    """
    icons_found = []
    
    if not icons_html:
        return icons_found
    
    # Look for tooltip data-content (most reliable method)
    # Pattern: <span class="tooltip" ... data-content="Vegan">
    tooltips = re.findall(r'data-content="([^"]+)"', icons_html, re.IGNORECASE)
    
    for tooltip in tooltips:
        tooltip_clean = tooltip.strip()
        tooltip_lower = tooltip_clean.lower()
        
        # Direct match in mapping
        if tooltip_lower in DIETARY_ICONS:
            label = DIETARY_ICONS[tooltip_lower]
            if label not in icons_found:
                icons_found.append(label)
            continue
        
        # Handle exact matches for common Rice tooltip values
        # Rice uses: "Vegan", "Vegetarian", "Gluten", "Soy", "Milk", "Eggs", "Fish", "Shellfish", "Halal", "Sesame"
        tooltip_to_label = {
            'vegan': 'Vegan',
            'vegetarian': 'Vegetarian',
            'gluten': 'Gluten',
            'soy': 'Soy',
            'milk': 'Dairy',  # Rice uses "Milk" but we standardize to "Dairy"
            'egg': 'Eggs',
            'eggs': 'Eggs',
            'fish': 'Fish',
            'shellfish': 'Shellfish',
            'halal': 'Halal',
            'sesame': 'Sesame',
            'peanut': 'Peanuts',
            'peanuts': 'Peanuts',
            'tree nut': 'Tree Nuts',
            'tree nuts': 'Tree Nuts'
        }
        
        if tooltip_lower in tooltip_to_label:
            label = tooltip_to_label[tooltip_lower]
            if label not in icons_found:
                icons_found.append(label)
            continue
        
        # Fallback: partial match against DIETARY_ICONS keys
        for key, label in DIETARY_ICONS.items():
            if key in tooltip_lower or tooltip_lower in key:
                if label not in icons_found:
                    icons_found.append(label)
                break
    
    # Also check icon classes as fallback (for cases where tooltips might be missing)
    # Look for class="icons icon-only vegan" or similar
    icon_class_pattern = r'class="[^"]*icons[^"]*(?:icon-only|icon)[^"]*(vegan|vegetarian|gluten|soy|dairy|milk|egg|eggs|fish|shellfish|peanut|peanuts|tree.?nut|halal|sesame)[^"]*"'
    class_matches = re.findall(icon_class_pattern, icons_html, re.IGNORECASE)
    
    for match in class_matches:
        match_lower = match.lower()
        # Map to standardized label
        if match_lower == 'milk':
            label = 'Dairy'
        elif match_lower in ['egg', 'eggs']:
            label = 'Eggs'
        elif match_lower in DIETARY_ICONS:
            label = DIETARY_ICONS[match_lower]
        else:
            # Try to find in DIETARY_ICONS
            for key, label_val in DIETARY_ICONS.items():
                if key in match_lower:
                    label = label_val
                    break
            else:
                continue  # Skip if no match found
        
        if label not in icons_found:
            icons_found.append(label)
    
    return icons_found


def _current_week_key() -> str:
    """Return a key like '2025-W49' for the current ISO week (in UTC)."""
    today = datetime.now(timezone.utc).date()
    year, week, _ = today.isocalendar()
    return f"{year}-W{week:02d}"


BROWSER_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'identity',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Cache-Control': 'no-cache',
    'Pragma': 'no-cache',
}


def _download_servery_html(servery_path: str) -> str:
    """Download the servery page HTML straight from Rice's origin server.

    Why the cookie: dining.rice.edu sits behind a CDN (Fastly/Varnish) that keeps
    cached copies of the anonymous page for up to a year (`Cache-Control:
    max-age=31536000`). Those cached copies were rendered when the weekly-menu
    Views were empty, so a plain request returns a ~125KB page with *no* menu
    items. The response carries `Vary: Cookie`, and any request that carries a
    Drupal-style `SESS*` cookie is passed through to the origin, which renders the
    page fresh (full "View Day" + "View Week" content, `Age: 0`).

    Query-string cache busters do NOT work: the WAF answers 406 for some paths
    (e.g. baker-college-kitchen) whenever a query string is present.
    """
    url = f"https://dining.rice.edu/{servery_path}"
    # Random cookie name/value so no intermediate cache can ever serve us a stale copy.
    bypass_cookie = f"SESS{secrets.token_hex(8)}={secrets.token_hex(8)}"

    header_sets = [
        {**BROWSER_HEADERS, 'Cookie': bypass_cookie},
        # Progressively simpler fallbacks (WAF has historically returned 406 for some header combos)
        {
            'User-Agent': BROWSER_HEADERS['User-Agent'],
            'Accept': 'text/html,*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'identity',
            'Cookie': bypass_cookie,
        },
        {'User-Agent': BROWSER_HEADERS['User-Agent'], 'Accept': '*/*', 'Cookie': bypass_cookie},
        # Last resort: whatever the CDN has cached
        {**BROWSER_HEADERS},
    ]

    last_error = None
    for i, headers in enumerate(header_sets):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=20) as response:
                html = response.read().decode('utf-8', errors='replace')
                age = response.headers.get('Age')
                if i > 0:
                    print(f"Fetched {servery_path} with fallback header set {i + 1}")
                print(f"Fetched {servery_path}: {len(html)} bytes (CDN age={age})")
                return html
        except urllib.error.HTTPError as e:
            last_error = e
            print(f"HTTP {e.code} fetching {servery_path} with header set {i + 1}")
            continue
        except Exception as e:
            last_error = e
            print(f"Error fetching {servery_path} with header set {i + 1}: {e}")
            continue

    print(f"Error fetching menu for {servery_path} (all retries failed): {last_error}")
    return ""


def fetch_menu_with_icons(servery_path: str):
    """Fetch and extract the *weekly* ("View Week") menu with dietary icons for a single servery.

    Always goes to Rice's origin (see _download_servery_html). The in-memory cache
    in get_weekly_menu() limits this to once per servery every MENU_TTL_SECONDS
    unless the user explicitly presses "Refresh".
    """
    html = _download_servery_html(servery_path)
    if not html:
        return {}

    # The page contains two tabs rendered server-side:
    #   #block-weeklymenubystations  -> "View Day" (today's menu by station)
    #   #block-weeklylunch           -> "View Week" (MONDAY..SUNDAY, LUNCH/DINNER)
    # We only want the weekly one. The day headers (<h4 class="static-date">) only
    # exist in the weekly block, but slice to it explicitly so "View Day" items can
    # never leak in if Rice reorders the blocks.
    weekly_start = html.find('id="block-weeklylunch"')
    if weekly_start != -1:
        html = html[weekly_start:]
    else:
        print(f"Note: no weekly menu block found for {servery_path} (page may not have a weekly menu yet)")

    menu = defaultdict(lambda: {'breakfast': [], 'lunch': [], 'munch': [], 'dinner': []})
    days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
    
    # Find all day headers
    day_pattern = r'<h4 class="static-date">(MONDAY|TUESDAY|WEDNESDAY|THURSDAY|FRIDAY|SATURDAY|SUNDAY)</h4>'
    day_matches = list(re.finditer(day_pattern, html, re.IGNORECASE))
    
    for i, day_match in enumerate(day_matches):
        day_name = day_match.group(1).lower()
        day_start = day_match.end()
        
        if i + 1 < len(day_matches):
            day_end = day_matches[i + 1].start()
        else:
            # Use full remaining HTML, don't limit to 50000 chars
            day_end = len(html)
        
        day_section = html[day_start:day_end]
        
        # Find BREAKFAST, LUNCH, MUNCH and DINNER sections
        meal_pattern = r'<h2>(BREAKFAST|LUNCH|MUNCH|DINNER)</h2>'
        meal_matches = list(re.finditer(meal_pattern, day_section, re.IGNORECASE))
        
        for j, meal_match in enumerate(meal_matches):
            meal_name = meal_match.group(1).lower()
            meal_start = meal_match.end()
            
            if j + 1 < len(meal_matches):
                meal_end = meal_matches[j + 1].start()
            else:
                # Look for next day header
                next_day_match = re.search(r'<h4 class="static-date">', day_section[meal_start:])
                if next_day_match:
                    meal_end = meal_start + next_day_match.start()
                else:
                    # If no next day, find where the menu items actually end
                    # Look for the last menu item and stop there
                    last_mitem_match = list(re.finditer(r'<a class="mitem"', day_section[meal_start:], re.IGNORECASE))
                    if last_mitem_match:
                        # Find the closing </a> for the last menu item
                        last_start = meal_start + last_mitem_match[-1].start()
                        last_a_end = day_section[last_start:].find('</a>')
                        if last_a_end != -1:
                            meal_end = last_start + last_a_end + 4
                        else:
                            meal_end = len(day_section)
                    else:
                        meal_end = len(day_section)
            
            meal_section = day_section[meal_start:meal_end]
            
            # Extract menu items with their icons - look for the full mitem structure
            # First try to get items with their icon containers
            mitem_pattern = r'<a class="mitem"[^>]*>(.*?)</a>'
            mitem_matches = re.findall(mitem_pattern, meal_section, re.DOTALL | re.IGNORECASE)
            
            for mitem_html in mitem_matches:
                # Extract name
                name_match = re.search(r'<div class="mname">(.*?)</div>', mitem_html, re.DOTALL | re.IGNORECASE)
                if not name_match:
                    continue
                
                # Extract icons - get all tooltips from the entire menu item HTML
                # This is more reliable than trying to match nested divs
                icons_html = mitem_html  # Extract from entire item, not just micons div
                
                # Clean item name
                item = re.sub(r'<[^>]+>', '', name_match.group(1))
                item = re.sub(r'&amp;', '&', item)
                item = re.sub(r'&nbsp;', ' ', item)
                item = re.sub(r'&#039;', "'", item)
                item = re.sub(r'&quot;', '"', item)
                # Normalize all whitespace (tabs, newlines, multiple spaces) to single spaces
                item = re.sub(r'\s+', ' ', item)
                item = item.strip()
                
                if (3 < len(item) < 150 and 
                    not any(skip in item.lower() for skip in ['dietary', 'preference', 'view', 'filter', 'apply', 'kosher meals'])):
                    
                    # Extract icons
                    icons = extract_icons(icons_html)
                    
                    # Check if item already exists (avoid duplicates)
                    # Use case-insensitive comparison to catch duplicates like "Vegetable of the Day"
                    existing = None
                    item_lower = item.lower().strip()
                    for existing_item in menu[day_name][meal_name]:
                        if existing_item['name'].lower().strip() == item_lower:
                            existing = existing_item
                            break
                    
                    if existing:
                        # Merge icons if item already exists
                        for icon in icons:
                            if icon not in existing['icons']:
                                existing['icons'].append(icon)
                    else:
                        menu[day_name][meal_name].append({
                            'name': item,
                            'icons': icons
                        })
            
            # Fallback: if no items found with icons, try simple extraction
            if not menu[day_name][meal_name]:
                item_pattern = r'<div class="mname">(.*?)</div>'
                item_matches = re.findall(item_pattern, meal_section, re.DOTALL | re.IGNORECASE)
                
                for item_html in item_matches:
                    item = re.sub(r'<[^>]+>', '', item_html)
                    item = re.sub(r'&amp;', '&', item)
                    item = re.sub(r'&nbsp;', ' ', item)
                    item = re.sub(r'&#039;', "'", item)
                    item = re.sub(r'&quot;', '"', item)
                    # Normalize all whitespace (tabs, newlines, multiple spaces) to single spaces
                    item = re.sub(r'\s+', ' ', item)
                    item = item.strip()
                    
                    if (3 < len(item) < 150 and 
                        not any(skip in item.lower() for skip in ['dietary', 'preference', 'view', 'filter', 'apply', 'kosher meals'])):
                        menu[day_name][meal_name].append({
                            'name': item,
                            'icons': []
                        })
    
    return dict(menu)


def get_weekly_menu(servery_name: str, servery_path: str, force: bool = False):
    """
    Return the weekly menu for a servery, using a per-week in-memory cache.

    - At the start of a new ISO week (Monday), the cache key changes and we
      automatically discard the old cached data.
    - Within the same week, cached data is reused for MENU_TTL_SECONDS, then
      re-downloaded. Rice fills in later days mid-week and blanks out past
      days, so a week-long cache misses new items.
    - On re-download, days the new page has items for replace the cached ones;
      days it has blanked keep their cached items.
    - The merged menu is written to the persistent menu log, which also seeds
      the cache on a cold start.
    - force=True bypasses the cache and re-downloads from Rice (the "Refresh" button).
    """
    global MENU_CACHE

    week_key = _current_week_key()

    # If week changed, reset the entire cache
    if MENU_CACHE.get("week_key") != week_key:
        MENU_CACHE = {
            "week_key": week_key,
            "fetched_at": {},
            "menus": {}
        }

    cached = MENU_CACHE["menus"].get(servery_name)
    fetched_at = MENU_CACHE["fetched_at"].get(servery_name)
    if cached is None:
        # Fresh process (e.g. a serverless cold start): resume from this week's log
        logged = load_menu_log(week_key, servery_name)
        if logged:
            cached, fetched_at = logged.get("menu") or {}, logged.get("fetched_at")
            MENU_CACHE["menus"][servery_name] = cached
            MENU_CACHE["fetched_at"][servery_name] = fetched_at
    if not force and cached is not None and fetched_at:
        age = (datetime.now(CST) - datetime.fromisoformat(fetched_at)).total_seconds()
        if age < MENU_TTL_SECONDS:
            return cached

    # Otherwise, fetch fresh data and merge it over what we had this week
    fresh = fetch_menu_with_icons(servery_path)
    menu = dict(cached or {})
    for day, meals in fresh.items():
        if any(meals.values()):
            menu[day] = meals
    MENU_CACHE["menus"][servery_name] = menu
    MENU_CACHE["fetched_at"][servery_name] = datetime.now(CST).isoformat()
    save_menu_log(week_key, servery_name, {"fetched_at": MENU_CACHE["fetched_at"][servery_name], "menu": menu})
    if not fresh:
        print(f"Warning: No menu items extracted for {servery_name} (path: {servery_path})")
    return menu


def _menu_item_count(menu) -> int:
    return sum(len(items) for meals in (menu or {}).values() for items in meals.values())


def refresh_all_menus():
    """Re-download every servery's weekly menu from Rice, ignoring the cache TTL."""
    summary = {}
    for servery_name, servery_path in SERVERIES.items():
        menu = get_weekly_menu(servery_name, servery_path, force=True)
        summary[servery_name] = {
            'items': _menu_item_count(menu),
            'days': sorted(d for d, meals in menu.items() if any(meals.values())),
            'fetched_at': MENU_CACHE["fetched_at"].get(servery_name),
        }
    return summary


def cuisine_keyword(item_name, cuisine_key):
    """The word in item_name that makes it count as cuisine_key (e.g. "Panner"), or None."""
    exclude = CUISINE_EXCLUDE_PATTERNS.get(cuisine_key)
    if exclude and exclude.search(item_name):
        return None
    match = CUISINE_PATTERNS[cuisine_key].search(item_name)
    return match.group(0) if match else None


def matches_cuisine(item_name, cuisine):
    """Check if item matches cuisine"""
    cuisine_lower = cuisine.lower()
    # Unknown cuisines never match - prevents "french" matching "french fries"
    return any(key in cuisine_lower and cuisine_keyword(item_name, key) for key in CUISINE_PATTERNS)


def matches_dietary(item_data, dietary_filter):
    """Check if item matches dietary restriction"""
    dietary_lower = dietary_filter.lower().strip()
    icons = [icon.lower().strip() for icon in item_data.get('icons', [])]
    
    # Map common variations
    dietary_map = {
        'veg': 'vegetarian',
        'veggie': 'vegetarian',
        'veggies': 'vegetarian',
        'gluten-free': 'gluten',
        'no gluten': 'gluten',
        'lactose': 'dairy',
        'milk': 'dairy'
    }
    
    if dietary_lower in dietary_map:
        dietary_lower = dietary_map[dietary_lower]
    
    # Normalize dietary filter to match icon labels
    # Icons are stored as: "Vegan", "Vegetarian", "Soy", "Dairy", etc.
    # Map filter to expected icon name
    filter_to_icon = {
        'soy': 'soy',
        'vegan': 'vegan',
        'vegetarian': 'vegetarian',
        'gluten': 'gluten',
        'dairy': 'dairy',
        'egg': 'eggs',
        'eggs': 'eggs',
        'fish': 'fish',
        'shellfish': 'shellfish',
        'peanut': 'peanuts',
        'peanuts': 'peanuts',
        'tree nut': 'tree nuts',
        'tree nuts': 'tree nuts',
        'halal': 'halal',
        'sesame': 'sesame'
    }
    
    # Try exact match first
    if dietary_lower in filter_to_icon:
        expected_icon = filter_to_icon[dietary_lower]
        if expected_icon in icons:
            return True
    
    # Fallback: check if dietary matches any icon (substring match)
    for icon in icons:
        if dietary_lower == icon or dietary_lower in icon or icon in dietary_lower:
            return True
    
    return False


def fuzzy_match(query, text, threshold=0.75):
    """Fuzzy match for item names with typo tolerance"""
    query_lower = query.lower().strip()
    text_lower = text.lower()
    
    # Exact match (substring)
    if query_lower in text_lower:
        return True
    
    # Word-level matching - ALL words in query must appear in text
    query_words = query_lower.split()
    text_words = text_lower.split()
    
    if query_words:
        # Check if ALL query words appear in the text (as whole words or substrings)
        all_words_match = all(
            any(qw in tw or tw in qw for tw in text_words) 
            for qw in query_words
        )
        if all_words_match:
            return True
    
    # Sequence matcher for typo tolerance (only if query is short, like "naan")
    if len(query_lower) <= 10:  # Only use fuzzy matching for short queries
        ratio = SequenceMatcher(None, query_lower, text_lower).ratio()
        if ratio >= threshold:
            return True
    
    return False


def find_matching_serveries(cuisine_filter=None, dietary_filter=None, dietary_exclude=None, day_filter=None, meal_filter=None, item_filter=None, servery_filter=None, dietary_mode: str = "and"):
    """Find serveries matching filters
    
    Args:
        dietary_filter: Items that MUST contain these dietary restrictions (comma-separated)
        dietary_exclude: Items that MUST NOT contain these dietary restrictions (comma-separated)
        dietary_mode: 'and' or 'or' for combining multiple dietary_filter items
    """
    results = {}
    
    # Day order for chronological sorting
    DAY_ORDER = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
    MEAL_ORDER = ['breakfast', 'lunch', 'dinner']
    
    # Parse multiple cuisines if comma-separated
    cuisine_list = []
    if cuisine_filter:
        cuisine_list = [c.strip() for c in cuisine_filter.split(',') if c.strip()]
    
    # Parse multiple dietary filters if comma-separated (include)
    dietary_list = []
    if dietary_filter:
        dietary_list = [d.strip() for d in dietary_filter.split(',') if d.strip()]
    
    # Parse multiple dietary exclusions if comma-separated (exclude)
    dietary_exclude_list = []
    if dietary_exclude:
        dietary_exclude_list = [d.strip() for d in dietary_exclude.split(',') if d.strip()]

    # Determine if item_filter is a cuisine or specific item
    is_cuisine_search = False
    if item_filter and not cuisine_list and not dietary_filter:
        # Check if it matches a known cuisine
        item_lower = item_filter.lower()
        for cuisine_key in CUISINE_KEYWORDS.keys():
            if cuisine_key in item_lower or item_lower in cuisine_key:
                is_cuisine_search = True
                cuisine_list = [item_filter]
                item_filter = None
                break
    
    # Filter serveries if servery_filter is specified (can be comma-separated)
    serveries_to_check = {}
    if servery_filter:
        # Parse comma-separated serveries
        servery_list = [s.strip().lower() for s in servery_filter.split(',') if s.strip()]
        for servery_name, servery_path in SERVERIES.items():
            if servery_name.lower() in servery_list:
                serveries_to_check[servery_name] = servery_path
    else:
        serveries_to_check = SERVERIES
    
    for servery_name, servery_path in serveries_to_check.items():
        # Use weekly cache so we only hit Rice once per servery per ISO week
        menu = get_weekly_menu(servery_name, servery_path)
        
        if not menu:
            continue
        
        matching_items = []
        
        # Collect all items with their locations
        for day, meals in menu.items():
            # Check day filter
            if day_filter and day.lower() != day_filter.lower():
                continue
            
            # Check all meal types (breakfast, lunch, munch, dinner)
            for meal_type in ['breakfast', 'lunch', 'munch', 'dinner']:
                # Check meal filter
                # If filtering by munch, also check lunch items (since munch uses lunch menu)
                if meal_filter:
                    meal_filter_lower = meal_filter.lower()
                    if meal_filter_lower == 'munch':
                        # For munch filter, check both munch and lunch items
                        if meal_type.lower() not in ['munch', 'lunch']:
                            continue
                    elif meal_type.lower() != meal_filter_lower:
                        continue
                
                for item_data in meals.get(meal_type, []):
                    item_name = item_data['name']
                    
                    # Check item filter (specific item search) - if provided, MUST match
                    # Use strict matching for item searches
                    item_match = True
                    if item_filter:
                        item_filter_lower = item_filter.lower().strip()
                        item_name_lower = item_name.lower()
                        # Require exact substring match for item searches (no fuzzy matching)
                        item_match = item_filter_lower in item_name_lower
                        if not item_match:
                            continue  # Skip this item if it doesn't match the item filter
                    
                    # Check cuisine filter(s) - match if item matches ANY selected cuisine
                    cuisine_match = True
                    if cuisine_list:
                        cuisine_match = any(matches_cuisine(item_name, cuisine) for cuisine in cuisine_list)
                        if not cuisine_match:
                            continue  # Skip if cuisine doesn't match
                    
                    # Check dietary filter(s) - items that MUST contain these
                    dietary_match = True
                    if dietary_list:
                        if dietary_mode == "or":
                            # At least one selected dietary must match
                            dietary_match = any(matches_dietary(item_data, d) for d in dietary_list)
                        else:
                            # Default: ALL selected dietaries must match
                            dietary_match = all(matches_dietary(item_data, d) for d in dietary_list)
                        if not dietary_match:
                            continue  # Skip if dietary doesn't match the chosen mode
                    
                    # Check dietary exclusions - items that MUST NOT contain these
                    if dietary_exclude_list:
                        # Item must NOT contain ANY of the excluded dietaries
                        has_excluded = any(matches_dietary(item_data, d) for d in dietary_exclude_list)
                        if has_excluded:
                            continue  # Skip if item contains any excluded dietary restriction
                    
                    # All filters passed, add this item
                    if item_match and cuisine_match and dietary_match:
                        # Track which cuisines this item matched (for coloring in UI)
                        matched_cuisines = []
                        for cuisine in cuisine_list or []:
                            if matches_cuisine(item_name, cuisine):
                                matched_cuisines.append(cuisine)
                        
                        # Check if this servery is currently open and serving this meal
                        current_meal, is_open = get_current_meal_and_status(servery_name, day)
                        is_currently_available = is_open and current_meal == meal_type
                        
                        # If filtering by munch and this is a lunch item, check if servery has munch
                        # and only include if it does
                        final_meal_type = meal_type
                        if meal_filter and meal_filter.lower() == 'munch':
                            if meal_type == 'lunch':
                                # Only include lunch items if servery has munch on this day
                                day_map = {
                                    'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
                                    'friday': 4, 'saturday': 5, 'sunday': 6
                                }
                                day_num = day_map.get(day.lower())
                                if day_num is not None:
                                    schedule = DINING_SCHEDULE.get(servery_name.lower(), {})
                                    day_schedule = schedule.get(day_num, [])
                                    has_munch = any(mt == 'munch' for mt, _, _ in day_schedule)
                                    if not has_munch:
                                        continue  # Skip lunch items from serveries without munch
                                final_meal_type = 'munch'  # Display as munch
                            elif meal_type == 'munch':
                                final_meal_type = 'munch'

                        matching_items.append({
                            'name': item_name,
                            'icons': item_data['icons'],
                            'day': day,
                            'meal': final_meal_type,
                            'servery': servery_name,
                            'matched_cuisines': matched_cuisines,
                            'is_currently_available': is_currently_available
                        })
        
        if matching_items:
            # Check if any items are currently available
            has_current_items = any(item.get('is_currently_available', False) for item in matching_items)
            results[servery_name] = {
                'items': matching_items,
                'count': len(matching_items),
                'has_current_items': has_current_items
            }
    
    # Sort items chronologically within each servery
    for servery_name in results:
        results[servery_name]['items'].sort(key=lambda x: (
            DAY_ORDER.index(x['day'].lower()) if x['day'].lower() in DAY_ORDER else 999,
            MEAL_ORDER.index(x['meal'].lower()) if x['meal'].lower() in MEAL_ORDER else 999
        ))
    
    # Sort serveries by number of matches (descending)
    results = dict(sorted(results.items(), key=lambda x: x[1]['count'], reverse=True))
    
    return results



# ---------------------------------------------------------------------------
# PDF export
# ---------------------------------------------------------------------------

# Phone-friendly page: narrow (half-letter) with large type, so a PDF viewer that
# fits the page to the screen width still shows comfortably readable text.
PDF_PAGE_SIZE = (5.5 * inch, 8.5 * inch)
PDF_MARGIN = 0.45 * inch

PDF_SERVERY_COLORS = {
    'north': '#2563eb',
    'south': '#059669',
    'west': '#7c3aed',
    'seibel': '#d97706',
    'baker': '#dc2626',
    'south main': '#db2777',
}
PDF_SERVERY_NAMES = {
    'north': 'North Servery',
    'south': 'South Servery',
    'west': 'West Servery',
    'seibel': 'Seibel Servery',
    'baker': 'Baker College Kitchen',
    'south main': 'South Main Servery',
}
PDF_DAY_ORDER = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
PDF_MEAL_ORDER = ['breakfast', 'lunch', 'munch', 'dinner']
# Positive dietary labels get a short green tag; everything else is an allergen.
PDF_DIET_TAGS = {'Vegan': 'VEGAN', 'Vegetarian': 'VEG', 'Halal': 'HALAL'}


def _pdf_styles():
    base = 'Helvetica'
    bold = 'Helvetica-Bold'
    return {
        'title': ParagraphStyle('title', fontName=bold, fontSize=20, leading=24, textColor=colors.HexColor('#0f172a')),
        'subtitle': ParagraphStyle('subtitle', fontName=base, fontSize=9.5, leading=13, textColor=colors.HexColor('#475569')),
        'legend': ParagraphStyle('legend', fontName=base, fontSize=8.5, leading=12, textColor=colors.HexColor('#64748b')),
        'day': ParagraphStyle('day', fontName=bold, fontSize=15, leading=19, textColor=colors.white, alignment=TA_LEFT),
        'meal': ParagraphStyle('meal', fontName=bold, fontSize=12, leading=15, textColor=colors.HexColor('#0f172a'),
                               spaceBefore=8, spaceAfter=4),
        'servery': ParagraphStyle('servery', fontName=bold, fontSize=11, leading=14, textColor=colors.white),
        'item': ParagraphStyle('item', fontName=base, fontSize=11, leading=14.5, textColor=colors.HexColor('#0f172a')),
        'tags': ParagraphStyle('tags', fontName=base, fontSize=8, leading=10.5, textColor=colors.HexColor('#64748b')),
        'empty': ParagraphStyle('empty', fontName=base, fontSize=12, leading=16, textColor=colors.HexColor('#475569')),
    }


def _pdf_item_paragraph(item, styles):
    """One menu item: bold-ish name, then a small line with diet tags / allergens."""
    name = xml_escape(item['name'])
    icons = item.get('icons') or []
    good = [PDF_DIET_TAGS[i] for i in icons if i in PDF_DIET_TAGS]
    allergens = [i for i in icons if i not in PDF_DIET_TAGS]

    parts = []
    for tag in good:
        parts.append(f'<font color="#059669"><b>{tag}</b></font>')
    if allergens:
        parts.append('<font color="#64748b">contains: ' + xml_escape(', '.join(a.lower() for a in allergens)) + '</font>')
    tag_line = ' &nbsp;·&nbsp; '.join(parts)

    text = name
    if tag_line:
        text += f'<br/><font size="8">{tag_line}</font>'
    return Paragraph(text, styles['item'])


def _describe_filters(f: Dict[str, str]) -> str:
    bits = []
    if f.get('day'):
        bits.append(f"Day: {f['day'].title()}")
    if f.get('meal'):
        bits.append(f"Meal: {f['meal'].title()}")
    if f.get('servery'):
        names = [PDF_SERVERY_NAMES.get(x.strip().lower(), x.strip().title()) for x in f['servery'].split(',') if x.strip()]
        bits.append("Serveries: " + ', '.join(names))
    if f.get('cuisine'):
        bits.append(f"Cuisine: {f['cuisine']}")
    if f.get('item'):
        bits.append(f"Item: \"{f['item']}\"")
    if f.get('dietary'):
        joiner = ' or ' if (f.get('dietary_mode') or 'and') == 'or' else ' and '
        bits.append("With: " + joiner.join(x.strip().title() for x in f['dietary'].split(',') if x.strip()))
    if f.get('dietary_exclude'):
        bits.append("Without: " + ', '.join(x.strip().title() for x in f['dietary_exclude'].split(',') if x.strip()))
    return ' · '.join(bits) if bits else 'No filters — full weekly menu'


def build_menu_pdf(results: Dict[str, Any], filters: Dict[str, str]) -> bytes:
    """Render search results (as returned by find_matching_serveries) to a PDF."""
    styles = _pdf_styles()
    page_w, page_h = PDF_PAGE_SIZE
    content_w = page_w - 2 * PDF_MARGIN
    now_cst = datetime.now(CST)

    # Regroup: day -> meal -> servery -> [items]
    grouped: Dict[str, Dict[str, Dict[str, list]]] = {}
    for servery_key, data in results.items():
        for it in data.get('items', []):
            grouped.setdefault(it['day'], {}).setdefault(it['meal'], {}).setdefault(servery_key, []).append(it)

    story = []
    story.append(Paragraph('OwlUCanEat — Weekly Menu', styles['title']))
    story.append(Spacer(1, 4))
    story.append(Paragraph(xml_escape(_describe_filters(filters)), styles['subtitle']))
    story.append(Paragraph(
        xml_escape(f"Week {MENU_CACHE.get('week_key') or ''} · generated {now_cst.strftime('%A, %b %-d %Y at %-I:%M %p')} CST · source: dining.rice.edu"),
        styles['subtitle']))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        '<font color="#059669"><b>VEGAN</b> / <b>VEG</b> / <b>HALAL</b></font> = dietary label from Rice. '
        '"contains: …" lists the allergens Rice flags for that item.', styles['legend']))
    story.append(Spacer(1, 10))

    def band(text, color_hex, style, pad=5):
        t = Table([[Paragraph(text, style)]], colWidths=[content_w])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(color_hex)),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), pad),
            ('BOTTOMPADDING', (0, 0), (-1, -1), pad),
            ('ROUNDEDCORNERS', [4, 4, 4, 4]),
        ]))
        return t

    total_items = 0
    days = [d for d in PDF_DAY_ORDER if d in grouped] + sorted(d for d in grouped if d not in PDF_DAY_ORDER)
    for day in days:
        meals = [m for m in PDF_MEAL_ORDER if m in grouped[day]] + sorted(m for m in grouped[day] if m not in PDF_MEAL_ORDER)
        for mi, meal in enumerate(meals):
            heading = [Paragraph(meal.title(), styles['meal'])]
            if mi == 0:
                # Keep the day band glued to the first meal heading
                heading = [band(day.upper(), '#0f172a', styles['day'], pad=7), Spacer(1, 2)] + heading
            serveries = sorted(grouped[day][meal].keys(),
                               key=lambda k: list(PDF_SERVERY_NAMES).index(k) if k in PDF_SERVERY_NAMES else 99)
            for si, servery_key in enumerate(serveries):
                items = grouped[day][meal][servery_key]
                total_items += len(items)
                color = PDF_SERVERY_COLORS.get(servery_key, '#475569')
                header = Paragraph(xml_escape(PDF_SERVERY_NAMES.get(servery_key, servery_key.title())), styles['servery'])
                rows = [[header]] + [[_pdf_item_paragraph(it, styles)] for it in items]
                # Header is row 0 of the same table: it repeats if the table splits across
                # pages, and NOSPLIT keeps it with the first item so it's never orphaned.
                table = Table(rows, colWidths=[content_w], repeatRows=1)
                table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(color)),
                    ('TOPPADDING', (0, 0), (-1, 0), 4),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 4),
                    ('LINEBELOW', (0, 1), (-1, -2), 0.4, colors.HexColor('#e2e8f0')),
                    ('LINEBEFORE', (0, 1), (0, -1), 2.5, colors.HexColor(color)),
                    ('LEFTPADDING', (0, 0), (-1, -1), 8),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                    ('TOPPADDING', (0, 1), (-1, -1), 4),
                    ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
                    ('NOSPLIT', (0, 0), (-1, min(1, len(rows) - 1))),
                ]))
                if si == 0:
                    story.append(KeepTogether(heading + [table]) if len(rows) <= 4 else KeepTogether(heading))
                    if len(rows) > 4:
                        story.append(table)
                else:
                    story.append(table)
                story.append(Spacer(1, 8))
        story.append(Spacer(1, 6))

    if total_items == 0:
        story.append(Paragraph("No menu items match these filters.", styles['empty']))

    footer_text = f"OwlUCanEat · {now_cst.strftime('%b %-d, %Y')}"

    def on_page(canvas, doc):
        canvas.saveState()
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(colors.HexColor('#94a3b8'))
        canvas.drawString(PDF_MARGIN, 0.28 * inch, footer_text)
        canvas.drawRightString(page_w - PDF_MARGIN, 0.28 * inch, f"Page {doc.page}")
        canvas.restoreState()

    buf = BytesIO()
    doc = BaseDocTemplate(buf, pagesize=PDF_PAGE_SIZE,
                          leftMargin=PDF_MARGIN, rightMargin=PDF_MARGIN,
                          topMargin=PDF_MARGIN, bottomMargin=PDF_MARGIN + 0.15 * inch,
                          title='OwlUCanEat weekly menu', author='OwlUCanEat')
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id='main',
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id='page', frames=[frame], onPage=on_page)])
    doc.build(story)
    return buf.getvalue()


class SearchRequest(BaseModel):
    cuisine: Optional[str] = None
    dietary: Optional[str] = None  # Items that MUST contain these (comma-separated)
    dietary_exclude: Optional[str] = None  # Items that MUST NOT contain these (comma-separated)
    dietary_mode: Optional[str] = None  # 'and' or 'or' for combining multiple dietary filters
    day: Optional[str] = None
    meal: Optional[str] = None
    item: Optional[str] = None
    servery: Optional[str] = None


@app.get("/api/current-time")
async def get_current_time():
    """API endpoint for getting current time (fast, no menu fetching)"""
    now_cst = datetime.now(CST)
    current_day_name = now_cst.strftime('%A').lower()
    current_time_str = now_cst.strftime('%I:%M %p')
    
    return JSONResponse(content={
        'day': current_day_name,
        'time': current_time_str,
        'timezone': 'CST'
    })


def get_all_currently_open_serveries():
    """Get all currently open serveries with their current meal types"""
    now_cst = datetime.now(CST)
    current_time = now_cst.time()
    current_weekday = now_cst.weekday()  # 0=Monday, 6=Sunday
    
    open_serveries = []
    
    for servery_name, schedule in DINING_SCHEDULE.items():
        day_schedule = schedule.get(current_weekday, [])
        
        if not day_schedule:
            continue
        
        # Check which meal period we're currently in
        for meal_type, start_time, end_time in day_schedule:
            if start_time <= current_time <= end_time:
                # Format meal type for display (capitalize, replace underscores)
                display_meal = meal_type.replace('_', ' ').title()
                open_serveries.append({
                    'servery': servery_name.title(),
                    'meal': display_meal,
                    'meal_type': meal_type
                })
                break  # Only one meal period at a time
    
    return open_serveries


@app.get("/api/currently-open")
async def get_currently_open():
    """API endpoint for getting all currently open serveries"""
    open_serveries = get_all_currently_open_serveries()
    return JSONResponse(content={
        'open_serveries': open_serveries,
        'count': len(open_serveries)
    })


@app.get("/api/schedule")
async def get_schedule():
    """API endpoint for getting the full dining schedule"""
    # Convert DINING_SCHEDULE to a format the frontend can use
    # Convert time objects to strings in HH:MM format
    schedule_data = {}
    for servery_name, servery_schedule in DINING_SCHEDULE.items():
        schedule_data[servery_name] = {}
        for day_num, meals in servery_schedule.items():
            schedule_data[servery_name][day_num] = [
                {
                    'meal_type': meal_type,
                    'start_time': f"{start_time.hour:02d}:{start_time.minute:02d}",
                    'end_time': f"{end_time.hour:02d}:{end_time.minute:02d}"
                }
                for meal_type, start_time, end_time in meals
            ]
    
    return JSONResponse(content={
        'schedule': schedule_data
    })


CUISINE_LABELS = {key: key.title() for key in CUISINE_KEYWORDS}


STATS_DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
STATS_DIETARY = ['Vegan', 'Vegetarian', 'Halal']


def _week_monday(week_key: str) -> Optional[date]:
    try:
        return date.fromisocalendar(int(week_key[:4]), int(week_key[6:]), 1)
    except ValueError:  # e.g. 2026-W60
        return None


def _shift_week(week_key: str, weeks: int) -> str:
    year, week, _ = (_week_monday(week_key) + timedelta(weeks=weeks)).isocalendar()
    return f"{year}-W{week:02d}"


def _range_label(from_key: str, to_key: str) -> str:
    """('2026-W44', '2026-W44') -> 'Oct 26 – Nov 1'; the year is added when the range crosses one."""
    monday, sunday = _week_monday(from_key), _week_monday(to_key) + timedelta(days=6)
    with_year = monday.year != sunday.year

    def fmt(d):
        return f"{d.strftime('%b')} {d.day}" + (f", {d.year}" if with_year else "")
    return f"{fmt(monday)} – {fmt(sunday)}"


def range_menus(from_key: str, to_key: str) -> Dict[Tuple[str, str], Dict[str, Any]]:
    """{(week_key, servery): menu} for a range: the live (cached) menus for the current week, the log for the rest."""
    current = _current_week_key()
    menus = load_menu_logs(from_key, to_key)
    if from_key <= current <= to_key:
        for name, path in SERVERIES.items():
            menus[(current, name)] = get_weekly_menu(name, path)
    return menus


def compute_stats(from_key: str, to_key: str) -> Dict[str, Any]:
    """Count what each servery served between two ISO weeks (inclusive).

    A "dish" is one menu line at one meal, so a dish served at lunch and dinner
    counts twice. A "meal" is one (day, lunch/dinner) service at one servery;
    cuisine meals count the services with at least one dish of that cuisine.
    The current week comes from the live (cached) menus, earlier weeks from the log.
    """
    current = _current_week_key()
    menus = range_menus(from_key, to_key)
    week_count = (_week_monday(to_key) - _week_monday(from_key)).days // 7 + 1

    by_servery = {}
    per_day = Counter()
    days_logged = set()
    dish_counts = Counter()
    dish_names = {}
    dish_serveries = defaultdict(set)
    dish_cuisines = defaultdict(set)

    for servery_name in SERVERIES:
        stats = {'dishes': 0, 'meals': 0, 'cuisine_dishes': Counter(), 'cuisine_meals': Counter(),
                 'dietary': Counter()}
        for (week_key, logged_servery), menu in menus.items():
            if logged_servery != servery_name:
                continue
            for day in STATS_DAYS:
                for items in (menu.get(day) or {}).values():
                    if not items:
                        continue
                    stats['meals'] += 1
                    days_logged.add((week_key, day))
                    cuisines_this_meal = set()
                    for item in items:
                        name = item['name']
                        stats['dishes'] += 1
                        per_day[day] += 1
                        for cuisine in CUISINE_KEYWORDS:
                            if matches_cuisine(name, cuisine):
                                stats['cuisine_dishes'][cuisine] += 1
                                cuisines_this_meal.add(cuisine)
                                dish_cuisines[name.lower()].add(cuisine)
                        for tag in STATS_DIETARY:
                            if tag in item.get('icons', []):
                                stats['dietary'][tag] += 1
                        key = name.lower()
                        dish_counts[key] += 1
                        dish_names.setdefault(key, name)
                        dish_serveries[key].add(servery_name)
                    for cuisine in cuisines_this_meal:
                        stats['cuisine_meals'][cuisine] += 1
        by_servery[servery_name] = {
            'name': servery_name.title(),
            'dishes': stats['dishes'],
            'meals': stats['meals'],
            'cuisine_dishes': dict(stats['cuisine_dishes']),
            'cuisine_meals': dict(stats['cuisine_meals']),
            'dietary': {tag: stats['dietary'][tag] for tag in STATS_DIETARY},
        }

    weeks = sorted(set(list_logged_weeks()) | {current}, reverse=True)
    presets = [{'label': 'This week', 'from': current, 'to': current}]
    if weeks[-1] < current:
        last_week = _shift_week(current, -1)
        presets += [
            {'label': 'Last week', 'from': last_week, 'to': last_week},
            {'label': 'Last 4 weeks', 'from': _shift_week(current, -3), 'to': current},
            {'label': 'All time', 'from': weeks[-1], 'to': current},
        ]
    cuisines_seen = {c for s in by_servery.values() for c in s['cuisine_dishes']}
    return {
        'range': {'from': from_key, 'to': to_key, 'label': _range_label(from_key, to_key), 'weeks': week_count},
        'current_week': current,
        'weeks': [{'key': w, 'label': _range_label(w, w)} for w in weeks],
        'presets': presets,
        'days_logged': len(days_logged),
        'days_in_range': 7 * week_count,
        'serveries': [{'key': k, 'name': k.title()} for k in SERVERIES],
        'cuisines': [{'key': k, 'name': CUISINE_LABELS[k]} for k in CUISINE_KEYWORDS],
        'totals': {
            'dishes': sum(per_day.values()),
            'unique_dishes': len(dish_counts),
            'meals': sum(s['meals'] for s in by_servery.values()),
            'cuisines_seen': len(cuisines_seen),
        },
        'by_servery': by_servery,
        'per_day': [{'day': d, 'dishes': per_day[d]} for d in STATS_DAYS],
        # 'all' plus one list per cuisine that appeared
        'top_dishes': {
            group: [
                {'name': dish_names[k], 'count': n, 'serveries': sorted(s.title() for s in dish_serveries[k])}
                for k, n in dish_counts.most_common() if group == 'all' or group in dish_cuisines[k]
            ][:10]
            for group in ['all', *sorted(cuisines_seen)]
        },
    }


def cuisine_cell_detail(from_key: str, to_key: str, servery_name: str, cuisine_key: str) -> Dict[str, Any]:
    """Every dish behind one square of the cuisine grid, grouped by meal in date order."""
    meals = []
    for (week_key, logged_servery), menu in sorted(range_menus(from_key, to_key).items()):
        if logged_servery != servery_name:
            continue
        monday = _week_monday(week_key)
        for day_index, day in enumerate(STATS_DAYS):
            for meal, items in (menu.get(day) or {}).items():
                dishes = [{'name': item['name'], 'keyword': keyword} for item in items or []
                          if (keyword := cuisine_keyword(item['name'], cuisine_key))]
                if dishes:
                    meals.append({'date': (monday + timedelta(days=day_index)).isoformat(), 'meal': meal,
                                  'dishes': dishes})
    meal_order = {'breakfast': 0, 'lunch': 1, 'munch': 2, 'dinner': 3}
    meals.sort(key=lambda m: (m['date'], meal_order.get(m['meal'], 9)))
    return {'servery': servery_name, 'cuisine': cuisine_key, 'meals': meals}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Main page"""
    # Indian first, then alphabetical
    supported_cuisines = sorted(CUISINE_LABELS.values(), key=lambda name: (name != 'Indian', name))
    # New-style signature (request first) - the old (name, {"request": ...}) form was removed in recent Starlette
    return templates.TemplateResponse(request, "index.html", {"supported_cuisines": supported_cuisines, "active_page": "menu"})


@app.get("/statistics", response_class=HTMLResponse)
async def statistics_page(request: Request):
    return templates.TemplateResponse(request, "stats.html", {"active_page": "statistics"})


def _stats_range(from_week: Optional[str], to_week: Optional[str]) -> Tuple[str, str]:
    """Validated (from, to) week keys; both default to the current week."""
    def valid(week_key):
        return week_key if week_key and WEEK_KEY_RE.match(week_key) and _week_monday(week_key) else None
    to_key = valid(to_week) or _current_week_key()
    from_key = valid(from_week) or to_key
    return (from_key, to_key) if from_key <= to_key else (to_key, from_key)


@app.get("/api/stats")
async def range_stats(from_week: Optional[str] = Query(None, alias="from"),
                      to_week: Optional[str] = Query(None, alias="to")):
    """Stats for ISO weeks from..to (inclusive), e.g. ?from=2026-W40&to=2026-W44. Defaults to this week."""
    return JSONResponse(content=compute_stats(*_stats_range(from_week, to_week)))


@app.get("/api/stats/cell")
async def stats_cell(servery: str, cuisine: str, from_week: Optional[str] = Query(None, alias="from"),
                     to_week: Optional[str] = Query(None, alias="to")):
    """The dishes behind one servery x cuisine square, for the same from..to range as /api/stats."""
    if servery not in SERVERIES or cuisine not in CUISINE_KEYWORDS:
        return JSONResponse(status_code=400, content={'error': 'unknown servery or cuisine'})
    from_key, to_key = _stats_range(from_week, to_week)
    return JSONResponse(content=cuisine_cell_detail(from_key, to_key, servery, cuisine))


@app.get("/api/cron/log-menus")
async def cron_log_menus(request: Request):
    """Daily Vercel cron: re-download every menu so each day is logged before Rice blanks it."""
    secret = os.environ.get("CRON_SECRET")
    if secret and request.headers.get("authorization") != f"Bearer {secret}":
        return JSONResponse(status_code=401, content={'error': 'unauthorized'})
    summary = refresh_all_menus()
    return JSONResponse(content={'week': _current_week_key(), 'serveries': summary})


@app.post("/api/refresh")
async def refresh_menus():
    """Force a fresh download of every servery's weekly menu from dining.rice.edu."""
    summary = refresh_all_menus()
    now_cst = datetime.now(CST)
    return JSONResponse(content={
        'refreshed_at': now_cst.strftime('%A %I:%M %p'),
        'week': MENU_CACHE.get("week_key"),
        'serveries': summary,
        'total_items': sum(v['items'] for v in summary.values()),
    })


def _normalized_filters(search_request: SearchRequest) -> Dict[str, str]:
    return {
        'cuisine': (search_request.cuisine or "").strip(),
        'dietary': (search_request.dietary or "").strip(),
        'dietary_exclude': (search_request.dietary_exclude or "").strip(),
        'dietary_mode': (search_request.dietary_mode or "and").strip().lower(),
        'day': (search_request.day or "").strip(),
        'meal': (search_request.meal or "").strip(),
        'item': (search_request.item or "").strip(),
        'servery': (search_request.servery or "").strip(),
    }


def _run_search(f: Dict[str, str]):
    return find_matching_serveries(
        cuisine_filter=f['cuisine'] or None,
        dietary_filter=f['dietary'] or None,
        dietary_exclude=f['dietary_exclude'] or None,
        dietary_mode=f['dietary_mode'],
        day_filter=f['day'] or None,
        meal_filter=f['meal'] or None,
        item_filter=f['item'] or None,
        servery_filter=f['servery'] or None,
    )


@app.post("/api/export")
async def export_pdf(search_request: SearchRequest):
    """Export the menu matching the given filters as a phone-friendly PDF."""
    f = _normalized_filters(search_request)
    results = _run_search(f)
    pdf_bytes = build_menu_pdf(results, f)
    scope = f['day'].lower() if f['day'] else 'week'
    filename = f"owlucaneat-menu-{scope}-{datetime.now(CST).strftime('%Y-%m-%d')}.pdf"
    return Response(content=pdf_bytes, media_type='application/pdf',
                    headers={'Content-Disposition': f'attachment; filename="{filename}"'})


@app.post("/api/search")
async def search(search_request: SearchRequest):
    """API endpoint for searching"""
    cuisine = (search_request.cuisine or "").strip()
    dietary = (search_request.dietary or "").strip()
    dietary_exclude = (search_request.dietary_exclude or "").strip()
    dietary_mode = (search_request.dietary_mode or "and").strip().lower()
    day = (search_request.day or "").strip()
    meal = (search_request.meal or "").strip()
    item = (search_request.item or "").strip()
    servery = (search_request.servery or "").strip()
    
    # Check for contradictory selections (same item in both include and exclude)
    if dietary and dietary_exclude:
        dietary_list = [d.strip().lower() for d in dietary.split(',') if d.strip()]
        dietary_exclude_list = [d.strip().lower() for d in dietary_exclude.split(',') if d.strip()]
        contradictions = set(dietary_list) & set(dietary_exclude_list)
        if contradictions:
            contradiction_items = ', '.join([item.title() for item in contradictions])
            return JSONResponse(
                status_code=400,
                content={
                    'error': f'Contradictory selection: You selected "{contradiction_items}" in both "Show items WITH these" and "Show items WITHOUT these". Please remove it from one section.',
                    'results': {},
                    'filters': {
                        'cuisine': cuisine,
                        'dietary': dietary,
                        'dietary_exclude': dietary_exclude,
                        'day': day,
                        'meal': meal,
                        'item': item,
                        'servery': servery
                    }
                }
            )
    
    # Allow empty filters - if all filters are empty, show all menu items
    results = find_matching_serveries(
        cuisine_filter=cuisine if cuisine else None,
        dietary_filter=dietary if dietary else None,
        dietary_exclude=dietary_exclude if dietary_exclude else None,
        dietary_mode=dietary_mode,
        day_filter=day if day else None,
        meal_filter=meal if meal else None,
        item_filter=item if item else None,
        servery_filter=servery if servery else None
    )
    
    # Get current time info for frontend
    now_cst = datetime.now(CST)
    current_day_name = now_cst.strftime('%A').lower()
    current_time_str = now_cst.strftime('%I:%M %p')
    
    return JSONResponse(content={
        'results': results,
        'filters': {
            'cuisine': cuisine,
            'dietary': dietary,
            'dietary_exclude': dietary_exclude,
            'day': day,
            'meal': meal,
            'item': item,
            'servery': servery
        },
        'current_time': {
            'day': current_day_name,
            'time': current_time_str,
            'timezone': 'CST'
        },
        'menu_fetched_at': dict(MENU_CACHE.get("fetched_at", {})),
    })


if __name__ == '__main__':
    import uvicorn
    import os
    PORT = int(os.environ.get("PORT", 5001))  # Use PORT env var for Fly.io, default to 5001 for local
    print("Starting Servery Finder Web App...")
    print(f"Open http://localhost:{PORT} in your browser")
    print(f"API docs available at http://localhost:{PORT}/docs")
    # Use import string format to enable reload mode
    reload = os.environ.get("ENV") != "production"  # Only reload in development
    uvicorn.run("servery_finder_web:app", host="0.0.0.0", port=PORT, reload=reload)
