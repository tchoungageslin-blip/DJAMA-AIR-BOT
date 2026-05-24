import urllib.request
import json

BASE = "https://djama-air-bot.vercel.app"

def post(path, body=None):
    data = json.dumps(body or {}).encode()
    req = urllib.request.Request(f"{BASE}{path}", data=data, headers={"Content-Type": "application/json"}, method="POST")
    return json.loads(urllib.request.urlopen(req).read().decode())

def get(path):
    req = urllib.request.Request(f"{BASE}{path}", method="GET")
    return json.loads(urllib.request.urlopen(req).read().decode())

print("=" * 60)
print("1. ALL ORDERS (last 10)")
print("=" * 60)
res = post("/api/debug/run-sql", {"sql": "SELECT order_number, order_type, status, created_at FROM orders ORDER BY created_at DESC LIMIT 10"})
for row in (res.get("result") or []):
    print(f"  {row['order_number']:10s} | {row['order_type']:15s} | {row['status']:10s} | {row['created_at']}")

print("\n" + "=" * 60)
print("2. CLIENT INFO")
print("=" * 60)
res2 = post("/api/debug/run-sql", {"sql": "SELECT id, phone_number, first_name FROM clients WHERE phone_number LIKE '%237670550135%' LIMIT 1"})
client_id = None
if res2.get("result"):
    c = res2["result"][0]
    client_id = c["id"]
    print(f"  ID: {client_id}")
    print(f"  Phone: {c['phone_number']}")
    print(f"  Name: {c['first_name']}")

print("\n" + "=" * 60)
print("3. SESSIONS for this client (last 5)")
print("=" * 60)
if client_id:
    res3 = post("/api/debug/run-sql", {"sql": f"SELECT id, status, current_intent, created_at, updated_at FROM sessions WHERE client_id = '{client_id}' ORDER BY created_at DESC LIMIT 5"})
    for row in (res3.get("result") or []):
        print(f"  {row['id'][:8]}... | {row['status']:15s} | {row.get('current_intent','?'):10s} | {row['created_at']}")
    
    # Check if any session is still BOT_ACTIVE (should be RESOLVED after our fix)
    active = [r for r in (res3.get("result") or []) if r["status"] == "BOT_ACTIVE"]
    if active:
        print(f"\n  ⚠️  {len(active)} session(s) still BOT_ACTIVE - these may cause context mixing!")
    else:
        print(f"\n  ✅ No lingering BOT_ACTIVE sessions")

print("\n" + "=" * 60)
print("4. DASHBOARD API - Billetterie tab")
print("=" * 60)
try:
    dash_bl = get("/api/dashboard/orders?order_type=BILLETTERIE")
    bl_orders = dash_bl.get("orders", [])
    print(f"  Billetterie orders count: {len(bl_orders)}")
    for o in bl_orders[:5]:
        print(f"    {o.get('order_number','?'):10s} | {o.get('order_type','?'):15s} | {o.get('status','?')}")
except Exception as e:
    print(f"  ❌ Error: {e}")

print("\n" + "=" * 60)
print("5. DASHBOARD API - Fret Aérien tab")
print("=" * 60)
try:
    dash_fa = get("/api/dashboard/orders?order_type=FRET_AERIEN")
    fa_orders = dash_fa.get("orders", [])
    print(f"  Fret Aerien orders count: {len(fa_orders)}")
    for o in fa_orders[:5]:
        print(f"    {o.get('order_number','?'):10s} | {o.get('order_type','?'):15s} | {o.get('status','?')}")
except Exception as e:
    print(f"  ❌ Error: {e}")

print("\n" + "=" * 60)
print("6. ORDER TYPE DISTRIBUTION")
print("=" * 60)
res_dist = post("/api/debug/run-sql", {"sql": "SELECT order_type, COUNT(*) as cnt FROM orders GROUP BY order_type ORDER BY cnt DESC"})
for row in (res_dist.get("result") or []):
    print(f"  {row['order_type']:15s} : {row['cnt']}")

print("\n" + "=" * 60)
print("7. FA1003 DETAILS (the problematic order)")
print("=" * 60)
res_fa = post("/api/debug/run-sql", {"sql": "SELECT order_number, order_type, data, created_at FROM orders WHERE order_number LIKE '%FA%1003%' OR order_number = 'FA-1003' LIMIT 3"})
for row in (res_fa.get("result") or []):
    print(f"  Number: {row['order_number']}")
    print(f"  Type: {row['order_type']}")
    print(f"  Created: {row['created_at']}")
    data = row.get('data')
    if isinstance(data, str):
        data = json.loads(data)
    if data:
        print(f"  Data keys: {list(data.keys())}")
        print(f"  shipping_mode: {data.get('shipping_mode')}")
        print(f"  goods_nature: {data.get('goods_nature')}")
        print(f"  notes: {data.get('notes')}")
    print()

print("\nDone.")
