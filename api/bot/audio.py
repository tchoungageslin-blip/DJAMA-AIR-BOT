import os
import io
import tempfile
from typing import Optional
from openai import AsyncOpenAI
from api.config import settings

class AudioProcessor:
    """Processes audio messages (voice notes) using Whisper."""
    
    def __init__(self):
        # Prefer Groq for ultra-fast, free Whisper
        if settings.GROQ_API_KEY:
            self.client = AsyncOpenAI(
                api_key=settings.GROQ_API_KEY,
                base_url="https://api.groq.com/openai/v1"
            )
            self.model = "whisper-large-v3"
        # Fallback to OpenAI if configured
        elif settings.OPENAI_API_KEY:
            self.client = AsyncOpenAI(
                api_key=settings.OPENAI_API_KEY
            )
            self.model = "whisper-1"
        else:
            self.client = None
            self.model = None

    async def transcribe_audio(self, audio_data: bytes, mime_type: str = "audio/ogg") -> Optional[str]:
        """Transcribe audio bytes to text."""
        if not self.client:
            print("[AUDIO] No Groq or OpenAI API key configured for transcription.")
            return "[Message vocal non transcrit - Clé API manquante]"
            
        try:
            # Determine extension from mime type (WhatsApp usually sends audio/ogg)
            ext = ".ogg"
            if "mp4" in mime_type:
                ext = ".mp4"
            elif "mpeg" in mime_type or "mp3" in mime_type:
                ext = ".mp3"
            elif "wav" in mime_type:
                ext = ".wav"
                
            # We must use a named temporary file because the OpenAI client expects a file-like object with a name
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as temp_file:
                temp_file.write(audio_data)
                temp_path = temp_file.name
                
            try:
                with open(temp_path, "rb") as audio_file:
                    transcript = await self.client.audio.transcriptions.create(
                        file=audio_file,
                        model=self.model,
                        language="fr" # Force French language since users are mostly from Cameroon/Francophone
                    )
                return transcript.text
            finally:
                # Clean up the temp file
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                    
        except Exception as e:
            print(f"[AUDIO ERROR] Failed to transcribe: {e}")
            return f"[Erreur de transcription vocale: {str(e)}]"

audio_processor = AudioProcessor()
