import urllib.request
import json

BASE = "https://djama-air-bot.vercel.app"

def post(path, body=None):
    data = json.dumps(body or {}).encode()
    req = urllib.request.Request(f"{BASE}{path}", data=data, headers={"Content-Type": "application/json"}, method="POST")
    return json.loads(urllib.request.urlopen(req).read().decode())

# 1. Resolve all lingering BOT_ACTIVE sessions for this client
print("Resolving all BOT_ACTIVE sessions...")
res = post("/api/debug/run-sql", {
    "sql": """UPDATE sessions SET status = 'RESOLVED', updated_at = NOW() 
              WHERE client_id = 'b35bb74c-2210-4f97-8b82-9d6575d4866e' 
              AND status = 'BOT_ACTIVE'
              RETURNING id, status"""
})
print(json.dumps(res, indent=2))

# 2. Verify no more active sessions
print("\nVerifying no active sessions remain...")
res2 = post("/api/debug/run-sql", {
    "sql": """SELECT id, status FROM sessions 
              WHERE client_id = 'b35bb74c-2210-4f97-8b82-9d6575d4866e' 
              AND status NOT IN ('RESOLVED', 'CLOSED')"""
})
rows = res2.get("result") or []
if len(rows) == 0:
    print("✅ No active sessions remain - next message will create a fresh session")
else:
    print(f"⚠️ Still {len(rows)} active sessions!")
    print(json.dumps(rows, indent=2))

print("\nDone. Ready for testing.")
