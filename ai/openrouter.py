import logging
import asyncio
import random
import aiohttp
from config import settings

INTERVIEW_SYSTEM_PROMPT = """You are a Polish language interview assistant for Karta Polaka preparation."""
TEST_SYSTEM_PROMPT = """You are a strict Polish language assessment expert."""
WORD_SYSTEM_PROMPT = """You are a Polish language teacher. Always respond in the format: {polish_word}|{russian_translation}|{example_in_polish}|{example_translation_in_russian}."""

async def get_ai_response(prompt: str, system_prompt: str = None) -> str:
    api_key = getattr(settings, "GEMINI_API_KEY", None)
    if not api_key:
        return "⚠️ Ошибка: API ключ Google Gemini не добавлен в Render."

    # Формируем запрос к Gemini API
    contents = []
    if system_prompt:
        contents.append({"role": "user", "parts": [{"text": system_prompt}]})
    contents.append({"role": "user", "parts": [{"text": prompt}]})

    # ✅ Официальный эндпоинт и быстрая модель
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
    
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": api_key  # Ключ формата AQ... передается в заголовке
    }
    
    payload = {"contents": contents}

    max_retries = 3
    for attempt in range(max_retries):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload, timeout=45) as response:
                    if response.status == 200:
                        data = await response.json()
                        # Проверяем, что ответ не пустой и содержит текст
                        if "candidates" in data and len(data["candidates"]) > 0:
                            return data["candidates"][0]["content"]["parts"][0]["text"]
                        else:
                            return "⚠️ Модель вернула пустой ответ."
                    
                    error_text = await response.text()
                    logging.error(f"Gemini API error: {response.status} - {error_text}")
                    
                    # Если сервер перегружен или превышен лимит - ждем и пробуем снова
                    if response.status in [429, 500, 502, 503, 504]:
                        wait_time = (2 ** (attempt + 1)) + random.uniform(0, 1)
                        await asyncio.sleep(wait_time)
                        continue
                    
                    return f"Ошибка API: {response.status} - {error_text}"
        except Exception as e:
            logging.error(f"Error connecting to Gemini API: {e}")
            await asyncio.sleep(2)

    return "⚠️ Сервера Google перегружены. Пожалуйста, попробуйте позже."
