import json
import logging
import base64
from typing import Optional, Dict
from openai import AsyncOpenAI
from api.config import settings
from api.bot.prompts import VISION_PROMPT

logger = logging.getLogger("djama.vision")


class VisionProcessor:
    """Processes images and PDFs using GPT-4o Vision."""

    def _create_client(self) -> AsyncOpenAI:
        """Create a fresh client per request (avoids stale connections on Vercel serverless)."""
        return AsyncOpenAI(
            api_key=settings.OPENROUTER_API_KEY,
            base_url=settings.OPENROUTER_BASE_URL,
            max_retries=1,
            timeout=20.0,
        )

    async def analyze_image(self, image_data: bytes, media_type: str = "image/jpeg") -> Dict:
        """
        Analyze an image (photo of package, label, screenshot).
        Returns extracted data (dimensions, weight, nature, hazards).
        """
        base64_image = base64.b64encode(image_data).decode("utf-8")
        client = self._create_client()
        try:
            response = await client.chat.completions.create(
                model=settings.VISION_MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": VISION_PROMPT},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{media_type};base64,{base64_image}",
                                    "detail": "high",
                                },
                            },
                        ],
                    }
                ],
                max_tokens=500,
                temperature=0.1,
            )
        finally:
            await client.close()

        result_text = response.choices[0].message.content.strip()

        try:
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0].strip()
            elif "```" in result_text:
                result_text = result_text.split("```")[1].split("```")[0].strip()
            return json.loads(result_text)
        except json.JSONDecodeError:
            logger.warning("Vision: could not parse JSON response, returning raw text")
            return {
                "dimensions": {"length_cm": None, "width_cm": None, "height_cm": None},
                "weight_kg": None,
                "goods_nature": None,
                "quantity": None,
                "hazard_icons": [],
                "is_sensitive": False,
                "sensitive_reason": None,
                "additional_info": result_text,
                "confidence": "low",
            }

    def check_sensitive_content(self, extracted_data: Dict) -> tuple:
        """
        Check if extracted data indicates sensitive goods.
        Returns (is_sensitive: bool, reason: str or None).
        """
        sensitive_keywords = [
            "battery", "batterie", "pile", "lithium",
            "liquid", "liquide", "cosmétique", "cosmetic",
            "pharmaceutical", "pharmaceutique", "médicament", "medicine",
            "machine", "industriel", "industrial",
            "danger", "hazard", "flammable", "inflammable",
        ]

        if extracted_data.get("hazard_icons"):
            return True, f"Icônes de danger détectées: {', '.join(extracted_data['hazard_icons'])}"

        if extracted_data.get("is_sensitive"):
            return True, extracted_data.get("sensitive_reason", "Contenu sensible détecté par l'IA")

        nature = (extracted_data.get("goods_nature") or "").lower()
        for keyword in sensitive_keywords:
            if keyword in nature:
                return True, f"Nature sensible détectée: {nature}"

        return False, None


vision_processor = VisionProcessor()
