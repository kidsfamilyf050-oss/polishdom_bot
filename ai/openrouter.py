import aiohttp
import logging
from config import settings

async def get_ai_response(prompt: str, system_prompt: str = None) -> str:
    api_key = settings.GEMINI_API_KEY
    if not api_key:
        logging.warning("GEMINI_API_KEY not provided. Using fallback responses.")
        if system_prompt == WORD_SYSTEM_PROMPT:
            return "słowo|слово|To jest słowo.|Это слово."
        elif system_prompt == TEST_SYSTEM_PROMPT:
            return "A1" # Заглушка
        elif system_prompt == INTERVIEW_SYSTEM_PROMPT:
            return "Вы хорошо подготовлены к интервью."
        else:
            return "⚠️ Ошибка: API ключ Google Gemini не добавлен в Render."

    contents = []
    if system_prompt:
        contents.append({"role": "user", "parts": [{"text": system_prompt}]})
    contents.append({"role": "user", "parts": [{"text": prompt}]})

    # Используем актуальную модель Gemini 1.5 Flash
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    payload = {"contents": contents}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logging.error(f"Gemini API error: {response.status} - {error_text}")
                    return f"Ошибка API: {response.status} - {error_text}"
                data = await response.json()
                return data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        logging.error(f"Error in get_ai_response (Gemini): {str(e)}")
        return f"Ошибка при запросе к API: {str(e)}"

INTERVIEW_SYSTEM_PROMPT = """You are a Polish language interview assistant for Karta Polaka preparation. Conduct mock interviews in Russian."""
TEST_SYSTEM_PROMPT = """You are a strict Polish language assessment expert."""
WORD_SYSTEM_PROMPT = """You are a Polish language teacher. Always respond in the format: {polish_word}|{russian_translation}|{example_in_polish}|{example_translation_in_russian}."""
