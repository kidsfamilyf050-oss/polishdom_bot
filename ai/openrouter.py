import aiohttp
import logging
from config import settings

async def get_ai_response(prompt: str, system_prompt: str = None) -> str:
    api_key = getattr(settings, "GEMINI_API_KEY", None)
    if not api_key:
        logging.warning("GEMINI_API_KEY not provided. Using fallback responses.")
        # (Оставьте здесь ваши старые fallback-ответы, если они нужны)
        if system_prompt == WORD_SYSTEM_PROMPT:
            return "słowo|слово|To jest słowo.|Это слово."
        elif system_prompt == TEST_SYSTEM_PROMPT:
            return "Ваш уровень: [A2]. Вы показали базовые знания польского языка."
        elif system_prompt == INTERVIEW_SYSTEM_PROMPT:
            return "Вы хорошо подготовлены к интервью. Продолжайте практиковаться."
        else:
            return "Функция недоступна без API ключа Google Gemini."

    # Формируем запрос к Gemini API
    contents = []
    if system_prompt:
        contents.append({"role": "user", "parts": [{"text": system_prompt}]})
    contents.append({"role": "user", "parts": [{"text": prompt}]})

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

# Системные промпты для разных задач
INTERVIEW_SYSTEM_PROMPT = """You are a Polish language interview assistant for Karta Polaka (Polish Card) preparation.
Conduct mock interviews in Russian, helping users prepare for real Polish Card interviews.
Provide constructive feedback and suggestions for improvement.
Be encouraging and supportive while maintaining professionalism."""

TEST_SYSTEM_PROMPT = """You are a Polish language assessment expert. 
Evaluate the user's Polish language level based on their responses and provide detailed feedback in Russian.
Determine their level according to CEFR standards (A1, A2, B1, B2, C1, C2).
Provide specific recommendations for improvement and next steps in their language learning journey."""

WORD_SYSTEM_PROMPT = """You are a Polish language teacher. Generate a word in Polish based on the given topic. 
Always respond in the format: {polish_word}|{russian_translation}|{example_in_polish}|{example_translation_in_russian}
The word and example should be appropriate for the student's level. 
The translations MUST be in Russian.
The example should be a simple, practical sentence using the word in everyday life."""
