import httpx
import asyncio

async def test():
    token = "vx_live_d0be8d41c344a79f11b2ba8ead2eb00d6e5b94932e00f7a588115ed62f43a603"
    payload = {"to": "237670550135", "type": "text", "text": {"body": "Test webhook error check"}}
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    async with httpx.AsyncClient() as client:
        # URL 1
        r1 = await client.post("https://vendrix.net/api/v1/messages/send", json=payload, headers=headers)
        print(f"vendrix.net: {r1.status_code} - {r1.text}")
        
        # URL 2
        try:
            r2 = await client.post("https://api.vendrix.net/api/v1/messages/send", json=payload, headers=headers)
            print(f"api.vendrix.net: {r2.status_code} - {r2.text}")
        except Exception as e:
            print(f"api.vendrix.net failed: {e}")

        # URL 3
        try:
            r3 = await client.post("https://api.vendrix.net/v1/messages/send", json=payload, headers=headers)
            print(f"api.vendrix.net/v1: {r3.status_code} - {r3.text}")
        except Exception as e:
            print(f"api.vendrix.net/v1 failed: {e}")

if __name__ == "__main__":
    asyncio.run(test())
