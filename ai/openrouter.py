import logging
import asyncio
import random
from config import settings
from google import genai
from google.genai import types

# ==========================================
# СИСТЕМНЫЕ ПРОМПТЫ (ОНИ ДОЛЖНЫ БЫТЬ ЗДЕСЬ)
# ==========================================
INTERVIEW_SYSTEM_PROMPT = """You are a Polish language interview assistant for Karta Polaka (Polish Card) preparation.
Conduct mock interviews in Russian, helping users prepare for real Polish Card interviews.
Provide constructive feedback and suggestions for improvement.
Be encouraging and supportive while maintaining professionalism."""

TEST_SYSTEM_PROMPT = """You are a strict Polish language assessment expert. 
Evaluate the user's Polish language level based on their responses and provide detailed feedback in Russian.
Determine their level according to CEFR standards (A1, A2, B1, B2, C1, C2).
Provide specific recommendations for improvement and next steps in their language learning journey."""

WORD_SYSTEM_PROMPT = """You are a Polish language teacher. Generate a word in Polish based on the given topic. 
Always respond in the format: {polish_word}|{russian_translation}|{example_in_polish}|{example_translation_in_russian}
The word and example should be appropriate for the student's level. 
The translations MUST be in Russian.
The example should be a simple, practical sentence using the word in everyday life."""


# ==========================================
# ЛОГИКА РАБОТЫ С ИИ
# ==========================================
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
            if 'generateContent' not in model.supported_generation_methods:
                continue
            if 'flash' in model_name.lower():
                candidates.append(model_name)
    except Exception as e:
        logging.error(f"Не удалось получить список моделей: {e}")
        return "gemini-3.5-flash" # Запасной вариант

    if not candidates:
        return "gemini-3.5-flash"

    def version_key(name):
        try:
            parts = name.split('-')
            version_str = parts[1]
            return [int(x) for x in version_str.split('.')]
        except (IndexError, ValueError):
            return [0, 0]

    candidates.sort(key=version_key, reverse=True)
    _best_model_name = candidates[0]
    logging.info(f"Выбрана модель: {_best_model_name}")
    return _best_model_name

async def get_ai_response(prompt: str, system_prompt: str = None) -> str:
    api_key = settings.GEMINI_API_KEY
    if not api_key:
        if system_prompt == WORD_SYSTEM_PROMPT:
            return "słowo|слово|To jest słowo.|Это слово."
        elif system_prompt == TEST_SYSTEM_PROMPT:
            return "A1"
        elif system_prompt == INTERVIEW_SYSTEM_PROMPT:
            return "Вы хорошо подготовлены к интервью."
        else:
            return "⚠️ Ошибка: API ключ Google Gemini не добавлен в Render."

    client = genai.Client(api_key=api_key)
    model_name = await get_available_model(client)

    full_prompt = ""
    if system_prompt:
        full_prompt += f"{system_prompt}\n\n"
    full_prompt += prompt

    max_retries = 5
    for attempt in range(max_retries):
        try:
            response = await client.aio.models.generate_content(
                model=model_name,
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
            
            if "404" in error_msg or "not found" in error_msg.lower():
                global _best_model_name
                _best_model_name = None
                model_name = await get_available_model(client)
                continue

            logging.error(f"Ошибка Gemini API (SDK): {error_msg}")
            return f"Ошибка API: {error_msg}"

    return "⚠️ Не удалось получить ответ от ИИ после нескольких попыток. Сервера Google перегружены."
