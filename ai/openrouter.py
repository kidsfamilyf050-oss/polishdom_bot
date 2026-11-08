import logging
import asyncio
import random
import aiohttp
from config import settings

INTERVIEW_SYSTEM_PROMPT = """You are a Polish language interview assistant for Karta Polaka preparation."""
TEST_SYSTEM_PROMPT = """You are a strict Polish language assessment expert."""
WORD_SYSTEM_PROMPT = """You are a Polish language teacher. Always respond in the format: {polish_word}|{russian_translation}|{example_in_polish}|{example_translation_in_russian}."""

async def get_ai_response(prompt: str, system_prompt: str = None) -> str:
    api_key = getattr(settings, "OPENROUTER_API_KEY", None)
    if not api_key:
        return "⚠️ Ошибка: API ключ OpenRouter не добавлен в Render."

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "openrouter/free",
        "messages": messages,
        "temperature": 0.4,
        "max_tokens": 4096
    }

    max_retries = 5 # Увеличили количество попыток, чтобы обойти тупые модели
    for attempt in range(max_retries):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload, timeout=45) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        if "choices" in data and len(data["choices"]) > 0:
                            message = data["choices"][0].get("message", {})
                            content = message.get("content", "")
                            
                            # 🛡️ ЗАЩИТА ОТ РАЗМЫШЛЕНИЙ (Thinking Process)
                            if not content:
                                continue # Если пусто, пробуем еще раз
                                
                            lower_content = content.lower()
                            if "thinking process" in lower_content or "analyze user request" in lower_content or "internal monologue" in lower_content:
                                logging.warning("Модель начала 'думать вслух'. Пропускаем ответ и пробуем снова...")
                                await asyncio.sleep(1)
                                continue
                            
                            # Если ответ чистый, возвращаем его
                            return content
                    
                    error_text = await response.text()
                    logging.error(f"OpenRouter API error: {response.status} - {error_text}")
                    
                    if response.status in [429, 500, 502, 503, 504]:
                        wait_time = (2 ** (attempt + 1)) + random.uniform(0, 1)
                        await asyncio.sleep(wait_time)
                        continue
                    
                    return f"Ошибка API: {response.status} - {error_text}"
        except Exception as e:
            logging.error(f"Error connecting to OpenRouter: {e}")
            await asyncio.sleep(2)

    return "⚠️ Сервера OpenRouter вернули ошибку или модель запуталась. Попробуйте еще раз через минуту."
