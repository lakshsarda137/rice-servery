"""
Enhanced Servery Finder with Icon Extraction and Web Interface
"""

import urllib.request
import urllib.error
import re
import os
from collections import defaultdict
from difflib import SequenceMatcher
from datetime import datetime, timezone, time as dt_time
from typing import Optional, Dict, Any, Tuple
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import pytz

try:
    # Used to fetch pages that return 406/403 to basic HTTP clients.
    # `curl_cffi` can impersonate a real browser TLS fingerprint.
    from curl_cffi import requests as curl_requests  # type: ignore
except Exception:
    curl_requests = None  # type: ignore

app = FastAPI()
templates = Jinja2Templates(directory="templates")

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
    'indian': ['curry', 'masala', 'tikka', 'biryani', 'naan', 'dal', 'chana', 'samosas', 
               'tandoori', 'roti', 'ghee', 'cumin', 'turmeric', 'garam masala', 'basmati rice',
               'biryani', 'palak', 'paneer', 'tandoor', 'korma', 'vindaloo'],
    'chinese': ['kung pao', 'szechuan', 'szechwan', 'general tso', 'orange chicken', 'lo mein',
                'chow mein', 'fried rice', 'dumpling', 'wonton', 'peking', 'canton', 'hunan',
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
    'american': ['burger', 'fries', 'mac and cheese', 'meatloaf', 'shepherd\'s pie', 
                 'mashed potatoes', 'gravy', 'biscuit', 'cornbread']
}

SERVERIES = {
    'north': 'north-servery',
    'south': 'south-servery',
    'west': 'west-servery',
    'seibel': 'seibel-servery',
    'baker': 'baker-college-kitchen'
}

# Dining schedule (CST) - based on Fall Dining Schedule
# Format: {servery: {day_of_week: [(meal_type, start_time, end_time), ...]}}
# day_of_week: 0=Monday, 6=Sunday
# Meal types: breakfast, snack_period, lunch, munch, extended_dinner, dinner, late_night
DINING_SCHEDULE = {
    'seibel': {
        0: [('breakfast', dt_time(7, 30), dt_time(10, 0)), ('snack_period', dt_time(10, 0), dt_time(11, 0)), ('lunch', dt_time(11, 30), dt_time(14, 0)), ('dinner', dt_time(17, 0), dt_time(20, 0))],  # Mon
        1: [('breakfast', dt_time(7, 30), dt_time(10, 0)), ('snack_period', dt_time(10, 0), dt_time(11, 0)), ('lunch', dt_time(11, 30), dt_time(14, 0)), ('dinner', dt_time(17, 0), dt_time(20, 0))],  # Tue
        2: [('breakfast', dt_time(7, 30), dt_time(10, 0)), ('snack_period', dt_time(10, 0), dt_time(11, 0)), ('lunch', dt_time(11, 30), dt_time(14, 0)), ('dinner', dt_time(17, 0), dt_time(20, 0))],  # Wed
        3: [('breakfast', dt_time(7, 30), dt_time(10, 0)), ('snack_period', dt_time(10, 0), dt_time(11, 0)), ('lunch', dt_time(11, 30), dt_time(14, 0)), ('dinner', dt_time(17, 0), dt_time(20, 0))],  # Thu
        4: [('breakfast', dt_time(7, 30), dt_time(10, 0)), ('snack_period', dt_time(10, 0), dt_time(11, 0)), ('lunch', dt_time(11, 30), dt_time(14, 0))],  # Fri (no dinner)
        6: [('breakfast', dt_time(8, 0), dt_time(11, 0)), ('lunch', dt_time(11, 30), dt_time(14, 0)), ('munch', dt_time(15, 0), dt_time(17, 0)), ('dinner', dt_time(17, 30), dt_time(20, 30))],  # Sun
    },
    'north': {
        0: [('breakfast', dt_time(7, 30), dt_time(10, 0)), ('snack_period', dt_time(10, 0), dt_time(11, 0)), ('lunch', dt_time(11, 30), dt_time(14, 0)), ('dinner', dt_time(17, 0), dt_time(21, 0))],  # Mon
        1: [('breakfast', dt_time(7, 30), dt_time(10, 0)), ('snack_period', dt_time(10, 0), dt_time(11, 0)), ('lunch', dt_time(11, 30), dt_time(14, 0)), ('dinner', dt_time(17, 0), dt_time(21, 0))],  # Tue
        2: [('breakfast', dt_time(7, 30), dt_time(10, 0)), ('snack_period', dt_time(10, 0), dt_time(11, 0)), ('lunch', dt_time(11, 30), dt_time(14, 0)), ('dinner', dt_time(17, 0), dt_time(21, 0))],  # Wed
        3: [('breakfast', dt_time(7, 30), dt_time(10, 0)), ('snack_period', dt_time(10, 0), dt_time(11, 0)), ('lunch', dt_time(11, 30), dt_time(14, 0)), ('dinner', dt_time(17, 0), dt_time(21, 0))],  # Thu
        4: [('breakfast', dt_time(7, 30), dt_time(10, 0)), ('snack_period', dt_time(10, 0), dt_time(11, 0)), ('lunch', dt_time(11, 30), dt_time(14, 0))],  # Fri (no dinner)
        6: [('breakfast', dt_time(8, 0), dt_time(11, 0)), ('lunch', dt_time(11, 30), dt_time(14, 0)), ('munch', dt_time(15, 0), dt_time(17, 0)), ('dinner', dt_time(17, 30), dt_time(20, 30))],  # Sun
    },
    'south': {
        0: [('breakfast', dt_time(7, 30), dt_time(10, 30)), ('lunch', dt_time(11, 30), dt_time(13, 30)), ('munch', dt_time(14, 0), dt_time(16, 0)), ('snack_period', dt_time(16, 0), dt_time(17, 0)), ('extended_dinner', dt_time(17, 30), dt_time(21, 0))],  # Mon
        1: [('breakfast', dt_time(7, 30), dt_time(10, 30)), ('lunch', dt_time(11, 30), dt_time(13, 30)), ('munch', dt_time(14, 0), dt_time(16, 0)), ('snack_period', dt_time(16, 0), dt_time(17, 0)), ('extended_dinner', dt_time(17, 30), dt_time(21, 0))],  # Tue
        2: [('breakfast', dt_time(7, 30), dt_time(10, 30)), ('lunch', dt_time(11, 30), dt_time(13, 30)), ('munch', dt_time(14, 0), dt_time(16, 0)), ('snack_period', dt_time(16, 0), dt_time(17, 0)), ('extended_dinner', dt_time(17, 30), dt_time(21, 0))],  # Wed
        3: [('breakfast', dt_time(7, 30), dt_time(10, 30)), ('lunch', dt_time(11, 30), dt_time(13, 30)), ('munch', dt_time(14, 0), dt_time(16, 0)), ('snack_period', dt_time(16, 0), dt_time(17, 0)), ('extended_dinner', dt_time(17, 30), dt_time(21, 0))],  # Thu
        4: [('breakfast', dt_time(7, 30), dt_time(10, 30)), ('lunch', dt_time(11, 30), dt_time(13, 30)), ('munch', dt_time(14, 0), dt_time(16, 0)), ('snack_period', dt_time(16, 0), dt_time(17, 0)), ('extended_dinner', dt_time(17, 30), dt_time(21, 0))],  # Fri
        5: [('breakfast', dt_time(8, 0), dt_time(11, 0)), ('lunch', dt_time(11, 30), dt_time(14, 0)), ('munch', dt_time(15, 0), dt_time(17, 0)), ('dinner', dt_time(17, 30), dt_time(20, 30))],  # Sat
    },
    'west': {
        0: [('breakfast', dt_time(7, 30), dt_time(10, 0)), ('lunch', dt_time(11, 30), dt_time(13, 30)), ('munch', dt_time(14, 0), dt_time(16, 0)), ('snack_period', dt_time(16, 0), dt_time(17, 0)), ('dinner', dt_time(17, 30), dt_time(20, 0)), ('late_night', dt_time(21, 0), dt_time(23, 0))],  # Mon
        1: [('breakfast', dt_time(7, 30), dt_time(10, 0)), ('lunch', dt_time(11, 30), dt_time(13, 30)), ('munch', dt_time(14, 0), dt_time(16, 0)), ('snack_period', dt_time(16, 0), dt_time(17, 0)), ('dinner', dt_time(17, 30), dt_time(20, 0)), ('late_night', dt_time(21, 0), dt_time(23, 0))],  # Tue
        2: [('breakfast', dt_time(7, 30), dt_time(10, 0)), ('lunch', dt_time(11, 30), dt_time(13, 30)), ('munch', dt_time(14, 0), dt_time(16, 0)), ('snack_period', dt_time(16, 0), dt_time(17, 0)), ('dinner', dt_time(17, 30), dt_time(20, 0)), ('late_night', dt_time(21, 0), dt_time(23, 0))],  # Wed
        3: [('breakfast', dt_time(7, 30), dt_time(10, 0)), ('lunch', dt_time(11, 30), dt_time(13, 30)), ('munch', dt_time(14, 0), dt_time(16, 0)), ('snack_period', dt_time(16, 0), dt_time(17, 0)), ('dinner', dt_time(17, 30), dt_time(20, 0)), ('late_night', dt_time(21, 0), dt_time(23, 0))],  # Thu
        4: [('breakfast', dt_time(7, 30), dt_time(10, 0)), ('lunch', dt_time(11, 30), dt_time(13, 30)), ('munch', dt_time(14, 0), dt_time(16, 0)), ('snack_period', dt_time(16, 0), dt_time(17, 0)), ('dinner', dt_time(17, 30), dt_time(21, 0))],  # Fri (no late night, extended dinner)
        5: [('breakfast', dt_time(8, 0), dt_time(11, 0)), ('lunch', dt_time(11, 30), dt_time(14, 0)), ('munch', dt_time(15, 0), dt_time(17, 0)), ('dinner', dt_time(17, 30), dt_time(20, 30))],  # Sat
    },
    'baker': {
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
MENU_CACHE: Dict[str, Any] = {
    "week_key": None,
    "menus": {}
}


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


def _clean_html_text(s: str) -> str:
    s = re.sub(r"<[^>]+>", "", s)
    s = s.replace("&amp;", "&").replace("&nbsp;", " ").replace("&#039;", "'").replace("&quot;", '"')
    s = re.sub(r"\s+", " ", s).strip()
    return s


_WEEKLY_STATION_BLOCK_MAP = {
    # These Drupal view blocks correspond to (day, meal). The page's own JS toggles
    # visibility by weekday using these IDs.
    #
    # Blocks 2-8: Mon..Sun Lunch
    # Blocks 10-16: Mon..Sun Dinner
    2: ("monday", "lunch"),
    3: ("tuesday", "lunch"),
    4: ("wednesday", "lunch"),
    5: ("thursday", "lunch"),
    6: ("friday", "lunch"),
    7: ("saturday", "lunch"),
    8: ("sunday", "lunch"),
    10: ("monday", "dinner"),
    11: ("tuesday", "dinner"),
    12: ("wednesday", "dinner"),
    13: ("thursday", "dinner"),
    14: ("friday", "dinner"),
    15: ("saturday", "dinner"),
    16: ("sunday", "dinner"),
}


def _slice_station_block(html: str, block_num: int) -> Optional[str]:
    block_id = f'block-views-block-weekly-menu-by-stations-block-{block_num}'
    start = html.find(f'id="{block_id}"')
    if start == -1:
        start = html.find(f"id=\"{block_id}\"")
    if start == -1:
        return None

    # End at the next stations-block container OR when we hit the next top-level weekly menu section.
    search_tail = html[start + 1 :]
    candidates = []

    m_next_block = re.search(r'id="block-views-block-weekly-menu-by-stations-block-\d+"', search_tail, re.IGNORECASE)
    if m_next_block:
        candidates.append(start + 1 + m_next_block.start())

    for marker in [
        'id="block-weeklylunch"',
        'id="block-weeklymenuswitchingcode"',
        'id="block-dailystandarditems"',
    ]:
        pos = html.find(marker, start + 1)
        if pos != -1:
            candidates.append(pos)

    end = min(candidates) if candidates else len(html)
    return html[start:end]


def _fetch_weekly_menu_by_stations(servery_path: str) -> Dict[str, Dict[str, list]]:
    """
    Fetch weekly menu for South/West by parsing the server-rendered Drupal blocks.

    Important: The default page load does NOT include the block contents for basic HTTP clients.
    However, requesting the page with a non-default dietary filter value causes the server to
    render the full view HTML (including menu items) in the response. Empirically, this does
    not actually filter the items in the HTML we receive, but it reliably forces rendering.
    """
    if curl_requests is None:
        print("Error: curl_cffi is not installed; cannot fetch South/West weekly menus reliably.")
        return {}

    # Force server-side rendering of the weekly menu blocks.
    #
    # Important nuance:
    # - With `field_dietary_restrictions_value=All` (default), the response often omits
    #   the weekly menu blocks for non-browser clients.
    # - With a non-default value, the server returns fully rendered HTML, but it may
    #   filter out items matching that restriction.
    #
    # To approximate the true "View Week" (unfiltered) content while reducing the risk
    # of missing items, we union across the "WITHOUT ..." filters (4-12). Any single
    # WITHOUT-X filter only excludes items containing X; by unioning multiple, we can
    # recover those items from another fetch where X is not excluded.
    #
    # We stop early if we stop discovering new items.
    force_values_order = [9, 10, 11, 12, 8, 7, 6, 5, 4]
    max_no_new_rounds = 2

    menu = defaultdict(lambda: {"breakfast": [], "lunch": [], "munch": [], "dinner": []})
    block_map = _WEEKLY_STATION_BLOCK_MAP

    seen_by_bucket = defaultdict(set)  # (day, meal) -> {lower_name}
    consecutive_no_new = 0

    for v in force_values_order:
        url = f"https://dining.rice.edu/{servery_path}?field_dietary_restrictions_value={v}"
        try:
            resp = curl_requests.get(url, impersonate="chrome120", timeout=20)
            html = resp.text
        except Exception as e:
            print(f"Error fetching weekly menu blocks for {servery_path} (force={v}): {e}")
            continue

        new_this_round = 0
        for block_num, (day_key, meal_key) in block_map.items():
            block_html = _slice_station_block(html, block_num)
            if not block_html:
                continue

            mitem_pattern = r'<a class="mitem"[^>]*>(.*?)</a>'
            mitem_matches = re.findall(mitem_pattern, block_html, re.DOTALL | re.IGNORECASE)

            for mitem_html in mitem_matches:
                name_match = re.search(r'<div class="mname">(.*?)</div>', mitem_html, re.DOTALL | re.IGNORECASE)
                if not name_match:
                    continue

                item = _clean_html_text(name_match.group(1))
                if (3 < len(item) < 150 and not any(skip in item.lower() for skip in ['dietary', 'preference', 'view', 'filter', 'apply', 'kosher meals'])):
                    item_lower = item.lower().strip()
                    bucket_key = (day_key, meal_key)
                    if item_lower in seen_by_bucket[bucket_key]:
                        # Still allow icon enrichment below by merging into existing entry
                        pass
                    else:
                        seen_by_bucket[bucket_key].add(item_lower)
                        new_this_round += 1

                    icons = extract_icons(mitem_html)

                    existing = None
                    for existing_item in menu[day_key][meal_key]:
                        if existing_item["name"].lower().strip() == item_lower:
                            existing = existing_item
                            break

                    if existing:
                        for icon in icons:
                            if icon not in existing["icons"]:
                                existing["icons"].append(icon)
                    else:
                        menu[day_key][meal_key].append({"name": item, "icons": icons})

        if new_this_round == 0:
            consecutive_no_new += 1
            if consecutive_no_new >= max_no_new_rounds:
                break
        else:
            consecutive_no_new = 0

    # Ensure all days exist in output.
    for day_key in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]:
        _ = menu[day_key]

    return dict(menu)


def fetch_menu_with_icons(servery_path: str):
    """Fetch and extract weekly menu with dietary icons for a single servery.

    Note: We do NOT use a timestamp parameter as it causes Rice's website to return
    a different/cached menu version. The in-memory weekly cache ensures we still only
    hit Rice once per servery per ISO week from our side.
    """
    def _menu_total_items(m: Dict[str, Dict[str, list]]) -> int:
        total = 0
        for day_meals in (m or {}).values():
            if not isinstance(day_meals, dict):
                continue
            for meal_key in ("breakfast", "lunch", "munch", "dinner"):
                total += len(day_meals.get(meal_key, []) or [])
        return total

    # Optional: force Drupal block scraping for all serveries (except Baker).
    force_drupal = os.getenv("USE_DRUPAL_STATIONS", "").strip().lower() in ("1", "true", "yes", "on")
    if force_drupal and servery_path != "baker-college-kitchen":
        return _fetch_weekly_menu_by_stations(servery_path)

    # Don't use timestamp parameter - it causes Rice's website to return different/cached menu
    # Use the base URL without timestamp to get the current menu
    url = f"https://dining.rice.edu/{servery_path}"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'identity',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Cache-Control': 'max-age=0'
    }
    
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            html = response.read().decode('utf-8')
    except urllib.error.HTTPError as e:
        # Try with minimal headers if 406 error (for Baker)
        if e.code == 406:
            # Try progressively simpler header sets, and also try URL without timestamp
            header_sets = [
                {
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,*/*',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Accept-Encoding': 'identity'
                },
                {
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
                    'Accept': '*/*'
                },
                {
                    'User-Agent': 'Mozilla/5.0'
                }
            ]
            
            # Try with simpler headers
            html = None
            for i, simple_headers in enumerate(header_sets):
                try:
                    req = urllib.request.Request(url, headers=simple_headers)
                    with urllib.request.urlopen(req, timeout=10) as response:
                        html = response.read().decode('utf-8')
                        print(f"Successfully fetched {servery_path} with header set {i+1}")
                        break
                except Exception as e2:
                    continue
            
            if html is None:
                print(f"Error fetching menu for {servery_path} (all retries failed): {e}")
                return {}
        else:
            print(f"Error fetching menu for {servery_path}: {e}")
            return {}
    except Exception as e:
        print(f"Error fetching menu for {servery_path}: {e}")
        return {}
    
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
    
    parsed = dict(menu)

    # Fallback: if the static HTML parser extracted nothing, try the Drupal station blocks.
    # This is needed for South/West and also makes the approach robust if Rice changes markup.
    if _menu_total_items(parsed) == 0 and servery_path != "baker-college-kitchen":
        fallback = _fetch_weekly_menu_by_stations(servery_path)
        if _menu_total_items(fallback) > 0:
            return fallback

    return parsed


def get_weekly_menu(servery_name: str, servery_path: str):
    """
    Return the weekly menu for a servery, using a per-week in-memory cache.

    - At the start of a new ISO week (Monday), the cache key changes and we
      automatically discard the old cached data.
    - Within the same week, we fetch each servery from Rice once, then
      reuse that data for all subsequent searches.
    """
    global MENU_CACHE

    week_key = _current_week_key()

    # If week changed, reset the entire cache
    if MENU_CACHE["week_key"] != week_key:
        MENU_CACHE = {
            "week_key": week_key,
            "menus": {}
        }

    # If this servery is already cached for this week, return it
    if servery_name in MENU_CACHE["menus"]:
        return MENU_CACHE["menus"][servery_name]

    # Otherwise, fetch fresh data and cache it
    menu = fetch_menu_with_icons(servery_path)
    MENU_CACHE["menus"][servery_name] = menu
    if not menu:
        print(f"Warning: No menu items extracted for {servery_name} (path: {servery_path})")
    return menu


def matches_cuisine(item_name, cuisine):
    """Check if item matches cuisine"""
    cuisine_lower = cuisine.lower()
    item_lower = item_name.lower()
    
    # Get keywords for this cuisine
    keywords = []
    cuisine_found = False
    for key, words in CUISINE_KEYWORDS.items():
        if key in cuisine_lower:
            keywords.extend(words)
            cuisine_found = True
    
    if not cuisine_found:
        # If cuisine not in keywords, don't match - prevents "french" matching "french fries"
        return False
    else:
        keywords.append(cuisine_lower)
    
    # Only match if item contains actual cuisine keywords, not just the cuisine name
    # This prevents "french" matching "french fries"
    for keyword in keywords:
        if keyword in item_lower:
            return True
    return False


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


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Main page"""
    # Get list of supported cuisines from CUISINE_KEYWORDS
    # Fix capitalization for special cases
    cuisine_map = {
        'indian': 'Indian',
        'japanese': 'Japanese',
        'chinese': 'Chinese',
        'thai': 'Thai',
        'mexican': 'Mexican',
        'italian': 'Italian',
        'mediterranean': 'Mediterranean',
        'american': 'American',
        'asian': 'Asian',
        'french': 'French',
        'korean': 'Korean',
        'vietnamese': 'Vietnamese',
        'greek': 'Greek'
    }
    supported_cuisines = sorted([cuisine_map.get(cuisine.lower(), cuisine.title()) for cuisine in CUISINE_KEYWORDS.keys()])
    return templates.TemplateResponse("index.html", {
        "request": request,
        "supported_cuisines": supported_cuisines
    })


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
        }
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
