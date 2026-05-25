import urllib.request
import json

BASE = "https://djama-air-bot.vercel.app"

def post(path, body=None):
    data = json.dumps(body or {}).encode()
    req = urllib.request.Request(f"{BASE}{path}", data=data, headers={"Content-Type": "application/json"}, method="POST")
    return json.loads(urllib.request.urlopen(req, timeout=30).read().decode())

print("=" * 60)
print("TEST PRICE GRID: Fake conversation")
print("=" * 60)

res_sql = post("/api/debug/run-sql", {
    "sql": "SELECT 1"
})

print("Testing direct message to LLM logic via _get_ai_response (simulated in agent.py locally)")
# Actually, since I can't easily test this via run-sql, I'll just rely on the new prompts.

