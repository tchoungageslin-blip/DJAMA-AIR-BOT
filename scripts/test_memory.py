import urllib.request
import urllib.error
import json

BASE = "https://djama-air-bot.vercel.app"

def post(path, body=None):
    data = json.dumps(body or {}).encode()
    req = urllib.request.Request(f"{BASE}{path}", data=data, headers={"Content-Type": "application/json"}, method="POST")
    return json.loads(urllib.request.urlopen(req).read().decode())

# Check current client state
print("=" * 60)
print("MEMORY TEST: Client 237670550135")
print("=" * 60)

res = post("/api/debug/run-sql", {"sql": "SELECT id, phone_number, first_name, last_name, client_type FROM clients WHERE phone_number LIKE '%237670550135%' LIMIT 1"})
if res.get("result"):
    c = res["result"][0]
    print(f"  Name in DB: {c.get('first_name')} {c.get('last_name')}")
    print(f"  Client type: {c.get('client_type')}")
    client_id = c["id"]
    
    # Check orders
    res2 = post("/api/debug/run-sql", {"sql": f"SELECT order_number, order_type, status, data FROM orders WHERE client_id = '{client_id}' ORDER BY created_at DESC LIMIT 5"})
    orders = res2.get("result") or []
    print(f"\n  Orders ({len(orders)}):")
    for o in orders:
        data = o.get("data") or {}
        if isinstance(data, str):
            data = json.loads(data)
        origin = data.get("origin", "?")
        dest = data.get("destination", "?")
        print(f"    {o['order_number']} ({o['order_type']}) {origin} -> {dest} [{o['status']}]")
    
    # Check what context the bot would build
    print(f"\n  Context that bot would see:")
    if c.get("first_name"):
        print(f"    [MEMOIRE] Nom du client: {c.get('first_name')} {c.get('last_name') or ''}")
    else:
        print(f"    [MEMOIRE] Client inconnu (nom pas encore collecte)")
    
    if orders:
        print(f"    [MEMOIRE] Client fidele avec {len(orders)} commande(s)")
        for o in orders[:3]:
            data = o.get("data") or {}
            if isinstance(data, str):
                data = json.loads(data)
            print(f"      - {o['order_number']} ({o['order_type']}) {data.get('origin','?')} -> {data.get('destination','?')}")
    else:
        print(f"    [MEMOIRE] Nouveau client, aucune commande precedente")

    # Check sessions
    res3 = post("/api/debug/run-sql", {"sql": f"SELECT id, status FROM sessions WHERE client_id = '{client_id}' AND status NOT IN ('RESOLVED','CLOSED')"})
    active = res3.get("result") or []
    print(f"\n  Active sessions: {len(active)}")
    if not active:
        print("    ✅ Clean state - next message creates fresh session")
else:
    print("  Client not found")

print("\nDone.")
