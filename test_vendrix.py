import httpx
import asyncio

async def test():
    token = "vx_live_816099ed0c802459f432e1b0fb184f5005d8dd06160ed52d7c956e97b753bb44"
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
