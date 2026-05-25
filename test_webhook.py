import httpx
import asyncio
import json
import time

async def test():
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "test_entry_id",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"display_phone_number": "12345", "phone_number_id": "12345"},
                    "contacts": [{"profile": {"name": "Test User"}, "wa_id": "237670550135"}],
                    "messages": [{
                        "from": "237670550135",
                        "id": f"wamid.test.{int(time.time())}",
                        "timestamp": str(int(time.time())),
                        "text": {"body": "Bonjour, ceci est un test de la connexion webhook via Vendrix !"},
                        "type": "text"
                    }]
                },
                "field": "messages"
            }]
        }]
    }

    url = "https://djama-air-bot.vercel.app/api/webhook"
    
    print(f"Sending test payload to {url}...")
    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, timeout=30.0)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")

if __name__ == "__main__":
    asyncio.run(test())
