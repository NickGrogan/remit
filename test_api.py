"""Quick test to verify Elexon REMIT API connectivity and response shape."""
import requests
import json
from datetime import datetime, timedelta

BASE = "https://data.elexon.co.uk/bmrs/api/v1"
now = datetime.utcnow()
from_dt = (now - timedelta(hours=24)).strftime("%Y/%m/%d %H:%M")
to_dt = now.strftime("%Y/%m/%d %H:%M")

url = f"{BASE}/remit/list/by-publish"
params = {"from": from_dt, "to": to_dt, "format": "json", "latestRevisionOnly": "true"}

print(f"Fetching: {url}")
print(f"Params: {params}")
r = requests.get(url, params=params, timeout=30)
print(f"Status: {r.status_code}")
ct = r.headers.get("Content-Type", "")
print(f"Content-Type: {ct}")

if r.status_code == 200:
    data = json.loads(r.text)
    print(f"Top-level keys: {list(data.keys())}")
    items = data.get("data", [])
    print(f"Item count: {len(items)}")
    if items:
        print(f"First item keys: {list(items[0].keys())}")
        print(f"First item:\n{json.dumps(items[0], indent=2)}")
else:
    print(f"Response: {r.text[:500]}")
