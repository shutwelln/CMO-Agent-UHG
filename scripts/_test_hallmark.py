#!/usr/bin/env python3
"""Quick test to debug Hallmark JSON parsing."""
import httpx
import json
import re

resp = httpx.get(
    "https://stores.hallmark.com/ar/benton/",
    follow_redirects=True,
    headers={"User-Agent": "Mozilla/5.0"},
)

m = re.search(r"""\$config\.defaultListData\s*=\s*'(.*?)'\s*;""", resp.text, re.DOTALL)
if not m:
    m = re.search(r"""\$config\.defaultListData\s*=\s*'(.*?)'""", resp.text, re.DOTALL)

if m:
    raw = m.group(1)
    print(f"Raw length: {len(raw)}")
    print(f"First 300 chars repr: {repr(raw[:300])}")
    print()

    # Unescape JS string escapes using regex (left-to-right, one escape at a time)
    # This correctly handles double-escaping: \\" → \", \\/ → /
    import re as _re
    raw = _re.sub(r"\\(.)", lambda m: m.group(1), raw)

    print(f"After unescape, first 300 chars repr: {repr(raw[:300])}")
    print()

    try:
        data = json.loads(raw)
        print(f"SUCCESS: Parsed {len(data)} locations")
        for loc in data[:3]:
            print(f"  {loc.get('location_name')}: {loc.get('address_1')}, "
                  f"{loc.get('city')}, {loc.get('region')} {loc.get('post_code')}")
            print(f"    phone={loc.get('local_phone')} lat={loc.get('lat')} lng={loc.get('lng')}")
    except json.JSONDecodeError as e:
        print(f"FAILED: {e}")
        # Show context around error
        pos = e.pos
        print(f"Context around pos {pos}: {repr(raw[max(0,pos-20):pos+20])}")
else:
    print("No match found")
    # Check if defaultListData exists at all
    idx = resp.text.find("defaultListData")
    if idx >= 0:
        print(f"Found at index {idx}, context:")
        print(repr(resp.text[idx:idx+200]))
