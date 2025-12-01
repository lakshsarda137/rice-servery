"""
Enhanced Servery Finder with Icon Extraction and Web Interface
"""

import urllib.request
import re
from collections import defaultdict
from difflib import SequenceMatcher
from typing import Optional
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Dietary icons mapping
DIETARY_ICONS = {
    'vegan': 'Vegan',
    'vegetarian': 'Vegetarian',
    'gluten': 'Gluten',
    'soy': 'Soy',
    'dairy': 'Dairy',
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
                'sweet and sour', 'mapo', 'char siu', 'bao', 'dim sum', 'hot pot'],
    'asian': ['wok', 'stir fry', 'bulgogi', 'pad thai', 'sushi', 'ramen', 'kimchi', 
              'gochujang', 'hoisin', 'miso', 'teriyaki', 'jasmine rice', 'short grain rice',
              'spring roll', 'dumpling', 'pho', 'szechuan', 'kung pao'],
    'japanese': ['sushi', 'ramen', 'teriyaki', 'miso', 'tempura', 'udon', 'soba', 'yakitori',
                 'tonkatsu', 'katsu', 'wasabi', 'ginger', 'sake', 'tamari', 'dashi'],
    'thai': ['pad thai', 'tom yum', 'tom kha', 'green curry', 'red curry', 'massaman', 'panang',
             'larb', 'som tam', 'mango sticky rice', 'coconut milk', 'lemongrass', 'galangal',
             'fish sauce', 'prik khing', 'prik king'],
    'mexican': ['taco', 'fajita', 'burrito', 'quesadilla', 'enchilada', 'salsa', 'guacamole',
                'cilantro', 'chipotle', 'pinto beans', 'refried beans', 'tortilla', 'tostada',
                'pupusa', 'picadillo', 'elote'],
    'italian': ['pasta', 'pizza', 'lasagna', 'risotto', 'marinara', 'alfredo', 'parmesan',
                'mozzarella', 'bolognese', 'carbonara', 'pesto', 'focaccia'],
    'french': ['ratatouille', 'coq au vin', 'bouillabaisse', 'cassoulet', 'quiche', 'crepe',
               'croissant', 'brie', 'camembert', 'provencal', 'bourguignon', 'confit',
               'bechamel', 'hollandaise', 'duck confit', 'escargot'],
    'bbq': ['bbq', 'barbecue', 'smoked', 'ribs', 'pulled pork', 'brisket', 'grill'],
    'mediterranean': ['mezze', 'hummus', 'pita', 'garbanzo', 'tzatziki', 'olive', 'feta',
                      'tabbouleh', 'falafel', 'tahini', 'moussaka', 'spanakorizo'],
    'american': ['burger', 'fries', 'mac and cheese', 'meatloaf', 'shepherd\'s pie', 
                 'mashed potatoes', 'gravy', 'biscuit', 'cornbread'],
    'vegetarian': ['plant-based', 'tofu', 'vegetable', 'vegan'],
    'halal': ['halal']
}

SERVERIES = {
    'north': 'north-servery',
    'south': 'south-servery',
    'west': 'west-servery',
    'seibel': 'seibel-servery',
    'baker': 'baker-college-kitchen'
}


def extract_icons(icons_html):
    """Extract dietary icons from HTML"""
    icons_found = []
    
    if not icons_html:
        return icons_found
    
    # Look for tooltip data-content (most reliable)
    tooltips = re.findall(r'data-content="([^"]+)"', icons_html, re.IGNORECASE)
    for tooltip in tooltips:
        tooltip_lower = tooltip.lower().strip()
        # Direct match
        if tooltip_lower in DIETARY_ICONS:
            label = DIETARY_ICONS[tooltip_lower]
            if label not in icons_found:
                icons_found.append(label)
        else:
            # Partial match
            for key, label in DIETARY_ICONS.items():
                if key in tooltip_lower or tooltip_lower in key:
                    if label not in icons_found:
                        icons_found.append(label)
    
    # Also check icon classes as fallback
    icon_class_patterns = [
        r'class="[^"]*(?:icon|vegan|vegetarian|gluten|soy|dairy|egg|fish|shellfish|peanut|tree.?nut|halal|sesame)[^"]*"',
        r'vegan|vegetarian|gluten|soy|dairy|egg|fish|shellfish|peanut|tree.?nut|halal|sesame'
    ]
    
    for pattern in icon_class_patterns:
        matches = re.findall(pattern, icons_html, re.IGNORECASE)
        for match in matches:
            match_lower = match.lower()
            for key, label in DIETARY_ICONS.items():
                if key in match_lower:
                    if label not in icons_found:
                        icons_found.append(label)
    
    return icons_found


def fetch_menu_with_icons(servery_path):
    """Fetch and extract weekly menu with dietary icons.

    We add a dummy query parameter to the URL to aggressively bust any upstream caches.
    This ensures that when Rice updates the weekly menu, we always see the latest HTML
    instead of a cached copy from a previous week.
    """
    import time
    # Cache-busting query param so we don't accidentally get a stale weekly page
    url = f"https://dining.rice.edu/{servery_path}?_ts={int(time.time())}"
    
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
    except Exception as e:
        return {}
    
    menu = defaultdict(lambda: {'breakfast': [], 'lunch': [], 'dinner': []})
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
            day_end = min(day_start + 50000, len(html))
        
        day_section = html[day_start:day_end]
        
        # Find BREAKFAST, LUNCH and DINNER sections
        meal_pattern = r'<h2>(BREAKFAST|LUNCH|DINNER)</h2>'
        meal_matches = list(re.finditer(meal_pattern, day_section, re.IGNORECASE))
        
        for j, meal_match in enumerate(meal_matches):
            meal_name = meal_match.group(1).lower()
            meal_start = meal_match.end()
            
            if j + 1 < len(meal_matches):
                meal_end = meal_matches[j + 1].start()
            else:
                next_day_match = re.search(r'<h4 class="static-date">', day_section[meal_start:])
                if next_day_match:
                    meal_end = meal_start + next_day_match.start()
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
                item = item.strip()
                
                if (5 < len(item) < 150 and 
                    not any(skip in item.lower() for skip in ['dietary', 'preference', 'view', 'filter', 'apply', 'kosher meals'])):
                    
                    # Extract icons
                    icons = extract_icons(icons_html)
                    
                    # Check if item already exists (avoid duplicates)
                    existing = None
                    for existing_item in menu[day_name][meal_name]:
                        if existing_item['name'] == item:
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
                    item = item.strip()
                    
                    if (5 < len(item) < 150 and 
                        not any(skip in item.lower() for skip in ['dietary', 'preference', 'view', 'filter', 'apply', 'kosher meals'])):
                        menu[day_name][meal_name].append({
                            'name': item,
                            'icons': []
                        })
    
    return dict(menu)


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


def find_matching_serveries(cuisine_filter=None, dietary_filter=None, day_filter=None, meal_filter=None, item_filter=None):
    """Find serveries matching filters"""
    results = {}
    
    # Day order for chronological sorting
    DAY_ORDER = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
    MEAL_ORDER = ['breakfast', 'lunch', 'dinner']
    
    # Parse multiple cuisines if comma-separated
    cuisine_list = []
    if cuisine_filter:
        cuisine_list = [c.strip() for c in cuisine_filter.split(',') if c.strip()]
    
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
    
    for servery_name, servery_path in SERVERIES.items():
        menu = fetch_menu_with_icons(servery_path)
        
        if not menu:
            continue
        
        matching_items = []
        
        # Collect all items with their locations
        for day, meals in menu.items():
            # Check day filter
            if day_filter and day.lower() != day_filter.lower():
                continue
            
            # Check all meal types (breakfast, lunch, dinner)
            for meal_type in ['breakfast', 'lunch', 'dinner']:
                # Check meal filter
                if meal_filter and meal_type.lower() != meal_filter.lower():
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
                    
                    # Check dietary filter - if provided, MUST match
                    dietary_match = True
                    if dietary_filter:
                        dietary_match = matches_dietary(item_data, dietary_filter)
                        if not dietary_match:
                            continue  # Skip if dietary doesn't match
                    
                    # All filters passed, add this item
                    if item_match and cuisine_match and dietary_match:
                        matching_items.append({
                            'name': item_name,
                            'icons': item_data['icons'],
                            'day': day,
                            'meal': meal_type,
                            'servery': servery_name
                        })
        
        if matching_items:
            results[servery_name] = {
                'items': matching_items,
                'count': len(matching_items)
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
    dietary: Optional[str] = None
    day: Optional[str] = None
    meal: Optional[str] = None
    item: Optional[str] = None


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Main page"""
    # Get list of supported cuisines from CUISINE_KEYWORDS
    # Fix capitalization for special cases
    cuisine_map = {
        'bbq': 'BBQ',
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
        'halal': 'Halal',
        'vegetarian': 'Vegetarian'
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
    day = (search_request.day or "").strip()
    meal = (search_request.meal or "").strip()
    item = (search_request.item or "").strip()
    
    if not cuisine and not dietary and not day and not meal and not item:
        return JSONResponse(
            status_code=400,
            content={
                'error': 'Please provide at least one filter',
                'results': {},
                'filters': {
                    'cuisine': cuisine,
                    'dietary': dietary,
                    'day': day,
                    'meal': meal,
                    'item': item
                }
            }
        )
    
    results = find_matching_serveries(
        cuisine_filter=cuisine if cuisine else None,
        dietary_filter=dietary if dietary else None,
        day_filter=day if day else None,
        meal_filter=meal if meal else None,
        item_filter=item if item else None
    )
    
    return JSONResponse(content={
        'results': results,
        'filters': {
            'cuisine': cuisine,
            'dietary': dietary,
            'day': day,
            'meal': meal,
            'item': item
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

