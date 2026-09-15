"""Test the API endpoint."""
import requests, json
r = requests.get("http://localhost:5000/api/alerts", timeout=10)
data = r.json()
print(f"Alert count: {data['count']}")
a = data["alerts"][0]
print(f"Latest: {a['headline']}")
print(f"Severity: {a['severity']}, Type: {a['event_type']}")
r2 = requests.get("http://localhost:5000/api/stats", timeout=10)
print(f"Stats: {json.dumps(r2.json(), indent=2)}")
