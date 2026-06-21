import json
import logging
import base64
from typing import Optional, Dict
from openai import AsyncOpenAI
from api.config import settings
from api.bot.prompts import VISION_PROMPT

logger = logging.getLogger("djama.vision")

PDF_MIME_TYPES = {"application/pdf", "application/x-pdf"}


class VisionProcessor:
    """Processes images and PDFs using Gemini 2.0 Flash via OpenRouter."""

    def _create_client(self) -> AsyncOpenAI:
        """Create a fresh client per request (avoids stale connections on Vercel serverless)."""
        return AsyncOpenAI(
            api_key=settings.OPENROUTER_API_KEY,
            base_url=settings.OPENROUTER_BASE_URL,
            max_retries=1,
            timeout=30.0,
        )

    def _is_pdf(self, media_type: str) -> bool:
        return (media_type or "").lower() in PDF_MIME_TYPES

    async def analyze_image(self, image_data: bytes, media_type: str = "image/jpeg") -> Dict:
        """
        Analyze an image or PDF document.
        - Images: sent as base64 image_url (vision)
        - PDFs: sent via OpenRouter's native PDF support with pdf-text engine (free)
        Returns extracted data (dimensions, weight, nature, hazards).
        """
        base64_data = base64.b64encode(image_data).decode("utf-8")
        client = self._create_client()

        if self._is_pdf(media_type):
            # OpenRouter native PDF support — pdf-text engine is free for digital PDFs
            # Falls back to mistral-ocr automatically for scanned PDFs
            content = [
                {"type": "text", "text": VISION_PROMPT},
                {
                    "type": "file",
                    "file": {
                        "filename": "document.pdf",
                        "content": base64_data,
                    },
                },
            ]
            logger.info("Vision: processing PDF document (%d bytes)", len(image_data))
        else:
            # Standard image (JPEG, PNG, WEBP, etc.)
            content = [
                {"type": "text", "text": VISION_PROMPT},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{media_type};base64,{base64_data}",
                        "detail": "high",
                    },
                },
            ]
            logger.info("Vision: processing image %s (%d bytes)", media_type, len(image_data))

        try:
            response = await client.chat.completions.create(
                model=settings.VISION_MODEL,
                messages=[{"role": "user", "content": content}],
                max_tokens=500,
                temperature=0.1,
                extra_body={"plugins": [{"id": "file-parser", "pdf": {"engine": "pdf-text"}}]} if self._is_pdf(media_type) else {},
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
