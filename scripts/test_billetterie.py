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

CLIENT_ID = "b35bb74c-2210-4f97-8b82-9d6575d4866e"

# TEST 1: Insert a BILLETTERIE order directly to verify the DB accepts it
print("=" * 60)
print("TEST 1: Direct BILLETTERIE insert via SQL")
print("=" * 60)
res = post("/api/debug/run-sql", {
    "sql": f"""INSERT INTO orders (id, order_number, client_id, order_type, status, data, created_at, updated_at)
    VALUES (gen_random_uuid(), 'BL-TESTFIX-001', '{CLIENT_ID}', 'BILLETTERIE', 'NOUVEAU', 
    '{{"origin":"Douala","destination":"Paris","goods_nature":"Vol aller-retour, 2 passagers, classe eco","notes":"Test billetterie fix"}}'::jsonb, 
    NOW(), NOW())
    RETURNING order_number, order_type, status"""
})
if res.get("result"):
    print(f"  ✅ Order created: {res['result'][0]}")
else:
    print(f"  ❌ Error: {res}")

# TEST 2: Check dashboard sees this BILLETTERIE order
print("\n" + "=" * 60)
print("TEST 2: Dashboard API - Billetterie tab")
print("=" * 60)
try:
    dash = get("/api/dashboard/orders?order_type=BILLETTERIE")
    orders = dash.get("orders", [])
    print(f"  Billetterie orders: {len(orders)}")
    found_test = False
    for o in orders:
        marker = " ← NEW" if "TESTFIX" in o.get("order_number","") else ""
        print(f"    {o.get('order_number','?'):15s} | {o.get('order_type','?'):12s} | {o.get('status','?')}{marker}")
        if "TESTFIX" in o.get("order_number",""):
            found_test = True
    if found_test:
        print("  ✅ New BILLETTERIE order visible on dashboard!")
    else:
        print("  ❌ New BILLETTERIE order NOT visible!")
except Exception as e:
    print(f"  ❌ API Error: {e}")

# TEST 3: Verify Fret Aerien tab does NOT show BILLETTERIE orders
print("\n" + "=" * 60)
print("TEST 3: Dashboard API - Fret Aérien should NOT have BILLETTERIE")
print("=" * 60)
try:
    dash_fa = get("/api/dashboard/orders?order_type=FRET_AERIEN")
    fa_orders = dash_fa.get("orders", [])
    bl_in_fa = [o for o in fa_orders if "BILLETTERIE" in (o.get("order_type","") or "")]
    if not bl_in_fa:
        print("  ✅ No BILLETTERIE orders in Fret Aerien tab")
    else:
        print(f"  ❌ Found {len(bl_in_fa)} BILLETTERIE orders in Fret Aerien tab!")
except Exception as e:
    print(f"  ❌ API Error: {e}")

# TEST 4: Check badges endpoint
print("\n" + "=" * 60)
print("TEST 4: Badges endpoint")
print("=" * 60)
try:
    badges = get("/api/dashboard/orders/badges")
    print(f"  Badges: {json.dumps(badges, indent=4)}")
except Exception as e:
    print(f"  ❌ Badges Error: {e}")

# TEST 5: Status update endpoint
print("\n" + "=" * 60)
print("TEST 5: Update order status")
print("=" * 60)
# Get the test order ID
res_id = post("/api/debug/run-sql", {"sql": "SELECT id FROM orders WHERE order_number = 'BL-TESTFIX-001' LIMIT 1"})
if res_id.get("result"):
    oid = res_id["result"][0]["id"]
    try:
        data = json.dumps({"status": "PRIS_EN_CHARGE"}).encode()
        req = urllib.request.Request(
            f"{BASE}/api/dashboard/orders/{oid}/status",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        status_res = json.loads(urllib.request.urlopen(req).read().decode())
        print(f"  ✅ Status update: {status_res}")
    except Exception as e:
        print(f"  ❌ Status update error: {e}")

# CLEANUP: Remove test order
print("\n" + "=" * 60)
print("CLEANUP: Remove test order")
print("=" * 60)
res_del = post("/api/debug/run-sql", {"sql": "DELETE FROM orders WHERE order_number = 'BL-TESTFIX-001' RETURNING order_number"})
if res_del.get("result"):
    print(f"  ✅ Cleaned up: {res_del['result'][0]['order_number']}")
else:
    print(f"  ❌ Cleanup issue: {res_del}")

print("\n" + "=" * 60)
print("ALL TESTS COMPLETE")
print("=" * 60)
