import aiohttp
import logging
import asyncio
from config import settings

async def get_ai_response(prompt: str, system_prompt: str = None) -> str:
    api_key = settings.GEMINI_API_KEY
    if not api_key:
        logging.warning("GEMINI_API_KEY not provided. Using fallback responses.")
        if system_prompt == WORD_SYSTEM_PROMPT:
            return "słowo|слово|To jest słowo.|Это слово."
        elif system_prompt == TEST_SYSTEM_PROMPT:
            return "A1"
        elif system_prompt == INTERVIEW_SYSTEM_PROMPT:
            return "Вы хорошо подготовлены к интервью."
        else:
            return "⚠️ Ошибка: API ключ Google Gemini не добавлен в Render."

    contents = []
    if system_prompt:
        contents.append({"role": "user", "parts": [{"text": system_prompt}]})
    contents.append({"role": "user", "parts": [{"text": prompt}]})

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={api_key}"
    payload = {"contents": contents}

    # --- Логика повторных попыток ---
    max_retries = 4  # Максимальное количество попыток
    for attempt in range(max_retries):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data["candidates"][0]["content"]["parts"][0]["text"]
                    
                    # Обрабатываем ошибки, которые можно повторить
                    if response.status in [429, 500, 502, 503, 504]:
                        wait_time = 2 ** (attempt + 1)  # 2, 4, 8, 16 секунд
                        logging.warning(f"Gemini API вернул {response.status}. Попытка {attempt + 1}/{max_retries}. Ждем {wait_time} сек...")
                        await asyncio.sleep(wait_time)
                        continue  # Переходим к следующей попытке
                    
                    # Для всех остальных ошибок (например, 400, 404) прекращаем попытки
                    error_text = await response.text()
                    logging.error(f"Gemini API error (не повторяем): {response.status} - {error_text}")
                    return f"Ошибка API: {response.status} - {error_text}"

        except aiohttp.ClientError as e:
            # Ошибка сети, тоже можно повторить
            wait_time = 2 ** (attempt + 1)
            logging.warning(f"Сетевая ошибка при запросе к Gemini: {e}. Попытка {attempt + 1}/{max_retries}. Ждем {wait_time} сек...")
            await asyncio.sleep(wait_time)
        except Exception as e:
            logging.error(f"Неизвестная ошибка в get_ai_response: {e}")
            return f"Ошибка при запросе к API: {str(e)}"

    # Если все попытки исчерпаны
    logging.error(f"Все {max_retries} попыток выполнить запрос к Gemini API провалились.")
    return "⚠️ Не удалось получить ответ от ИИ после нескольких попыток. Сервера Google перегружены. Попробуйте, пожалуйста, еще раз через пару минут."


INTERVIEW_SYSTEM_PROMPT = """You are a Polish language interview assistant for Karta Polaka preparation. Conduct mock interviews in Russian."""
TEST_SYSTEM_PROMPT = """You are a strict Polish language assessment expert."""
WORD_SYSTEM_PROMPT = """You are a Polish language teacher. Always respond in the format: {polish_word}|{russian_translation}|{example_in_polish}|{example_translation_in_russian}."""
