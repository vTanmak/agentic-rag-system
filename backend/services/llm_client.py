import asyncio
import logging
from typing import AsyncGenerator

from google import genai
from google.genai import types as genai_types
from groq import AsyncGroq
from tenacity import retry,retry_if_exception_type,stop_after_attempt,wait_exponential
from backend.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_genai_client = genai.Client(api_key=settings.gemini_api_key)

class LLMClient:
    def __init__(self):
        self._groq_client = AsyncGroq(api_key=settings.groq_api_key)
        self._use_groq_fallback = False

    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        reraise=True,
    )
    async def generate(self, prompt: str, system_prompt: str = "") -> str:
        if not self._use_groq_fallback:
            try:
                return await self._gemini_generate(prompt, system_prompt)
            except Exception as e:
                logger.warning(f"Gemini failed, switching to Groq: {e}")
                self._use_groq_fallback = True

        return await self._groq_generate(prompt, system_prompt)

    async def stream(
        self, prompt: str, system_prompt: str = ""
    ) -> AsyncGenerator[str, None]:
        if not self._use_groq_fallback:
            try:
                async for token in self._gemini_stream(prompt, system_prompt):
                    yield token
                return
            except Exception as e:
                logger.warning(f"Gemini stream failed, switching to Groq: {e}")
                self._use_groq_fallback = True

        async for token in self._groq_stream(prompt, system_prompt):
            yield token

    async def _gemini_generate(self, prompt: str, system_prompt: str) -> str:
        config = genai_types.GenerateContentConfig()
        if system_prompt:
            config.system_instruction = system_prompt
        
        response = await _genai_client.aio.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=config,
        )
        return response.text

    async def _gemini_stream(
        self, prompt: str, system_prompt: str
    ) -> AsyncGenerator[str, None]:
        config = genai_types.GenerateContentConfig()
        if system_prompt:
            config.system_instruction = system_prompt
            
        async for chunk in await _genai_client.aio.models.generate_content_stream(
            model=settings.gemini_model,
            contents=prompt,
            config=config,
        ):
            if chunk.text:
                yield chunk.text

    async def _groq_generate(self, prompt: str, system_prompt: str) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = await self._groq_client.chat.completions.create(
            model=settings.groq_model,
            messages=messages,
        )
        return response.choices[0].message.content

    async def _groq_stream(
        self, prompt: str, system_prompt: str
    ) -> AsyncGenerator[str, None]:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        stream = await self._groq_client.chat.completions.create(
            model=settings.groq_model,
            messages=messages,
            stream=True,
        )
        async for chunk in stream:
            token = chunk.choices[0].delta.content
            if token:
                yield token


llm_client = LLMClient()
