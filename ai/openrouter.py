import logging
import asyncio
import random
import aiohttp
from config import settings

INTERVIEW_SYSTEM_PROMPT = """You are a Polish language interview assistant for Karta Polaka preparation."""
TEST_SYSTEM_PROMPT = """You are a strict Polish language assessment expert."""
WORD_SYSTEM_PROMPT = """You are a Polish language teacher. Always respond in the format: {polish_word}|{russian_translation}|{example_in_polish}|{example_translation_in_russian}."""

async def list_available_models(api_key: str) -> list:
    """Получает список доступных моделей для генерации контента."""
    url = "https://generativelanguage.googleapis.com/v1beta/models"
    headers = {"x-goog-api-key": api_key}
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=20) as response:
                if response.status == 200:
                    data = await response.json()
                    models = []
                    for m in data.get("models", []):
                        # Ищем модели, которые поддерживают generateContent и являются Flash
                        if "generateContent" in m.get("supportedGenerationMethods", []):
                            name = m.get("name", "").replace("models/", "")
                            if "flash" in name.lower():
                                models.append(name)
                    return models
    except Exception as e:
        logging.error(f"Failed to list models: {e}")
    return []

async def get_ai_response(prompt: str, system_prompt: str = None) -> str:
    api_key = getattr(settings, "GEMINI_API_KEY", None)
    if not api_key:
        return "⚠️ Ошибка: API ключ Google Gemini не добавлен в Render."

    # 1. Получаем список доступных моделей
    available_models = await list_available_models(api_key)
    
    # Если список пуст, используем запасной вариант
    if not available_models:
        available_models = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash-latest"]

    # 2. Пробуем модели по очереди, пока одна не ответит
    for model_name in available_models:
        logging.info(f"Пробуем модель: {model_name}")
        
        contents = []
        if system_prompt:
            contents.append({"role": "user", "parts": [{"text": system_prompt}]})
        contents.append({"role": "user", "parts": [{"text": prompt}]})

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": api_key
        }
        payload = {"contents": contents}

        for attempt in range(2):  # 2 попытки на каждую модель
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, headers=headers, json=payload, timeout=45) as response:
                        if response.status == 200:
                            data = await response.json()
                            if "candidates" in data and len(data["candidates"]) > 0:
                                return data["candidates"][0]["content"]["parts"][0]["text"]
                        
                        error_text = await response.text()
                        logging.warning(f"Model {model_name} error: {response.status} - {error_text}")
                        
                        if response.status in [429, 500, 502, 503, 504]:
                            wait_time = (2 ** (attempt + 1)) + random.uniform(0, 1)
                            await asyncio.sleep(wait_time)
                            continue
                        
                        break  # Если ошибка не связана с перегрузкой, переходим к следующей модели
            except Exception as e:
                logging.error(f"Error connecting to {model_name}: {e}")
                await asyncio.sleep(1)

    return "⚠️ Все доступные модели Gemini сейчас перегружены. Пожалуйста, попробуйте через пару минут."
