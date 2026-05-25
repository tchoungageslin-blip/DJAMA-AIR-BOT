import asyncio
import base64
import json
from api.bot.vision import VisionProcessor

async def test_vision():
    print("=" * 60)
    print("TEST VISION: Simulating photo analysis")
    print("=" * 60)
    
    # Create a tiny 1x1 transparent GIF as a fake photo
    # In reality this would be a photo of a package or invoice
    fake_img = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")
    
    vp = VisionProcessor()
    
    try:
        print("Sending image to Vision AI...")
        res = await vp.analyze_image(fake_img, "image/gif")
        print("✅ Vision AI Response:")
        print(json.dumps(res, indent=2, ensure_ascii=False))
        if res.get("confidence") == "low":
            print("Note: Confidence is low because it's a blank 1x1 image, but the AI responded!")
    except Exception as e:
        print(f"❌ Vision Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_vision())
