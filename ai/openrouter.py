import logging
import asyncio
import random
from config import settings
from google import genai
from google.genai import types

INTERVIEW_SYSTEM_PROMPT = """You are a Polish language interview assistant for Karta Polaka preparation."""
TEST_SYSTEM_PROMPT = """You are a strict Polish language assessment expert."""
WORD_SYSTEM_PROMPT = """You are a Polish language teacher. Always respond in the format: {polish_word}|{russian_translation}|{example_in_polish}|{example_translation_in_russian}."""

_best_model_name = None

async def get_available_model(client: genai.Client) -> str:
    global _best_model_name
    if _best_model_name:
        return _best_model_name

    logging.info("Ищем лучшую доступную модель Gemini...")
    candidates = []
    try:
        pager = await client.aio.models.list()
        async for model in pager:
            model_name = model.name
            if 'flash' in model_name.lower():
                clean_name = model_name.replace("models/", "")
                candidates.append(clean_name)
    except Exception as e:
        logging.error(f"Не удалось получить список моделей: {e}")
        return "gemini-1.5-flash"

    if not candidates:
        return "gemini-1.5-flash"

    def version_key(name):
        try:
            parts = name.split('-')
            for p in parts:
                if '.' in p:
                    return [int(x) for x in p.split('.')]
            return [0, 0]
        except (IndexError, ValueError):
            return [0, 0]

    candidates.sort(key=version_key, reverse=True)
    _best_model_name = candidates[0]
    logging.info(f"✅ ВЫБРАНА МОДЕЛЬ: {_best_model_name}")
    return _best_model_name

async def get_ai_response(prompt: str, system_prompt: str = None) -> str:
    api_key = settings.GEMINI_API_KEY
    if not api_key:
        return "⚠️ Ошибка: API ключ Google Gemini не добавлен в Render."

    client = genai.Client(api_key=api_key)
    model_name = await get_available_model(client)
    full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt

    max_retries = 3
    for attempt in range(max_retries):
        try:
            # ✅ ТАЙМАУТ 30 СЕКУНД
            response = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=model_name,
                    contents=full_prompt,
                    config=types.GenerateContentConfig(temperature=0.3)
                ),
                timeout=30.0
            )
            return response.text
        except asyncio.TimeoutError:
            logging.warning(f"Таймаут Gemini. Попытка {attempt + 1}/{max_retries}.")
            await asyncio.sleep(2)
        except Exception as e:
            error_msg = str(e)
            if "404" in error_msg or "not found" in error_msg.lower():
                global _best_model_name
                _best_model_name = None
                model_name = await get_available_model(client)
                continue
            if any(code in error_msg for code in ["503", "429", "UNAVAILABLE", "ResourceExhausted"]):
                wait_time = (2 ** (attempt + 1)) + random.uniform(0, 1)
                await asyncio.sleep(wait_time)
                continue
            return f"Ошибка API: {error_msg}"

    return "⚠️ Сервера Google перегружены. Попробуйте позже."
