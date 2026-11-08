import logging
import asyncio
import random
from config import settings
from google import genai
from google.genai import types

# Глобальная переменная для кэширования найденной модели
_best_model_name = None

async def get_available_model(client: genai.Client) -> str:
    """Динамически находит и возвращает имя лучшей доступной модели."""
    global _best_model_name
    if _best_model_name:
        return _best_model_name

    logging.info("Ищем лучшую доступную модель Gemini...")
    candidates = []
    try:
        # Получаем список всех моделей
        pager = await client.aio.models.list()
        async for model in pager:
            model_name = model.name
            # Нас интересуют только модели, поддерживающие генерацию контента
            if 'generateContent' not in model.supported_generation_methods:
                continue
            
            # Отдаем предпочтение моделям Flash
            if 'flash' in model_name.lower():
                candidates.append(model_name)
    except Exception as e:
        logging.error(f"Не удалось получить список моделей: {e}")
        # В случае ошибки используем надежный псевдоним
        return "gemini-flash-latest"

    if not candidates:
        logging.warning("Не найдено ни одной подходящей модели Flash. Используем псевдоним.")
        return "gemini-flash-latest"

    # Сортируем, чтобы попытаться выбрать самую новую версию (например, 3.5, 3.6 и т.д.)
    # Это очень простой парсинг версии из имени модели
    def version_key(name):
        try:
            # Извлекаем числа из имени, например 'gemini-3.5-flash' -> [3, 5]
            parts = name.split('-')
            version_str = parts[1]
            return [int(x) for x in version_str.split('.')]
        except (IndexError, ValueError):
            return [0, 0]

    candidates.sort(key=version_key, reverse=True)
    best_model = candidates[0]
    _best_model_name = best_model
    logging.info(f"Выбрана модель: {best_model}")
    return best_model


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

    client = genai.Client(api_key=api_key)
    
    # ✅ ДИНАМИЧЕСКИЙ ВЫБОР МОДЕЛИ
    model_name = await get_available_model(client)

    full_prompt = ""
    if system_prompt:
        full_prompt += f"{system_prompt}\n\n"
    full_prompt += prompt

    max_retries = 5
    for attempt in range(max_retries):
        try:
            response = await client.aio.models.generate_content(
                model=model_name, # <-- Используем найденную модель
                contents=full_prompt,
                config=types.GenerateContentConfig(temperature=0.3)
            )
            return response.text

        except Exception as e:
            error_msg = str(e)
            if any(code in error_msg for code in ["503", "429", "UNAVAILABLE", "ResourceExhausted"]):
                wait_time = (2 ** (attempt + 1)) + random.uniform(0, 1)
                logging.warning(f"Gemini API перегружен. Попытка {attempt + 1}/{max_retries}. Ждем {wait_time:.1f} сек...")
                await asyncio.sleep(wait_time)
                continue
            
            # Если модель вдруг стала недоступна, сбрасываем кэш и пробуем найти новую
            if "404" in error_msg or "not found" in error_msg.lower():
                logging.warning(f"Модель {model_name} не найдена. Ищем новую...")
                global _best_model_name
                _best_model_name = None
                model_name = await get_available_model(client)
                continue # Пробуем еще раз с новой моделью

            logging.error(f"Ошибка Gemini API (SDK): {error_msg}")
            return f"Ошибка API: {error_msg}"

    return "⚠️ Не удалось получить ответ от ИИ после нескольких попыток. Сервера Google перегружены. Попробуйте, пожалуйста, еще раз через пару минут."

# ... (промпты остаются без изменений) ...
