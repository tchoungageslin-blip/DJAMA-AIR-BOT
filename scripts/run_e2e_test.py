import urllib.request
import urllib.error
import json

BASE = "https://djama-air-bot.vercel.app"

print("=" * 60)
print("END-TO-END TEST: Billetterie flow simulation")
print("=" * 60)
print("This test creates a fake billetterie conversation,")
print("calls the real LLM to classify it, creates an order,")
print("and verifies it's BILLETTERIE (not FRET_AERIEN).")
print("=" * 60)

data = json.dumps({}).encode()
req = urllib.request.Request(
    f"{BASE}/api/debug/test-billetterie",
    data=data,
    headers={"Content-Type": "application/json"},
    method="POST"
)

try:
    res = json.loads(urllib.request.urlopen(req, timeout=30).read().decode())
    print("\nResults:")
    print(json.dumps(res, indent=2, ensure_ascii=False))
    
    print("\n" + "=" * 60)
    if res.get("test_passed"):
        print("🎉 TEST PASSED! " + res.get("verdict", ""))
    else:
        print("💥 TEST FAILED! " + res.get("verdict", ""))
    print("=" * 60)
    
except urllib.error.HTTPError as he:
    body = he.read().decode()
    print(f"\n❌ HTTP {he.code}: {body[:2000]}")
except Exception as e:
    print(f"\n❌ Test request failed: {e}")
    import traceback
    traceback.print_exc()
