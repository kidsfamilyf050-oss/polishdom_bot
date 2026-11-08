import os
import uuid
import asyncio
import edge_tts
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from ai.openrouter import get_ai_response
from db.mongo import db

router = Router()

class LessonStates(StatesGroup):
    waiting_for_answers = State()

async def generate_audio_with_retry(text: str, filename: str):
    """Генерирует аудио с повторными попытками и запасным голосом."""
    # Список голосов для попыток
    voices_to_try = [
        "pl-PL-MarekNeural",  # Основной мужской голос
        "pl-PL-ZofiaNeural"   # Запасной женский голос
    ]
    
    for voice in voices_to_try:
        for attempt in range(3):  # 3 попытки для каждого голоса
            try:
                communicate = edge_tts.Communicate(text, voice)
                await communicate.save(filename)
                return True  # Успех
            except edge_tts.exceptions.NoAudioReceived:
                logging.warning(f"Не удалось получить аудио с голосом {voice}. Попытка {attempt + 1}/3.")
                await asyncio.sleep(1)  # Небольшая пауза перед повтором
            except Exception as e:
                logging.error(f"Неизвестная ошибка edge-tts с голосом {voice}: {e}")
                break  # Переходим к следующему голосу
    
    return False  # Все попытки провалились


@router.message(Command("lesson"))
async def cmd_lesson(message: Message, state: FSMContext):
    user = await db.get_user(message.from_user.id)
    level = user.get("language_level", "A0")
    name = user.get("name", "друг")
    
    await message.answer(f"🔄 {name}, готовлю урок для уровня {level}...")
    
    prompt = f"""
    Ты — опытный репетитор польского. Составь мини-урок для ученика уровня {level}.
    Структура:
    1. 5 новых слов с переводом.
    2. 1 правило грамматики (кратко).
    3. Короткий диалог (3-4 реплики) с переводом.
    4. 3 задания (перевод с русского на польский).
    
    ВАЖНО: Используй HTML-теги для форматирования! 
    Заголовки выделяй тегом <b>...</b>. Польские слова выделяй тегом <code>...</code>. 
    Переводы делай курсивом <i>...</i>. Не пиши лишнего текста, только урок.
    """
    
    lesson_text = await get_ai_response(prompt)
    await message.answer(lesson_text, parse_mode="HTML")
    
    # Генерируем аудио с повторными попытками
    audio_text = "Урок польского. Слушай внимательно."
    filename = f"audio_{uuid.uuid4().hex}.mp3"
    
    success = await generate_audio_with_retry(audio_text, filename)
    
    if success:
        await message.answer_voice(FSInputFile(filename), caption="🔊 Аудио к уроку")
        os.remove(filename)
    else:
        await message.answer("⚠️ Не удалось создать аудио. Попробуйте позже.")
        logging.error("Все попытки генерации аудио провалились.")
    
    await state.set_state(LessonStates.waiting_for_answers)
    await state.update_data(current_lesson=lesson_text)
    await message.answer("📝 Напиши ответы на 3 задания через точку с запятой (;).")


@router.message(LessonStates.waiting_for_answers)
async def check_lesson(message: Message, state: FSMContext):
    data = await state.get_data()
    lesson_text = data.get("current_lesson")
    user_answers = message.text
    
    await message.answer("🔄 Проверяю твои ответы...")
    
    prompt = f"""
    Вот текст урока:
    {lesson_text}
    
    Ученик прислал ответы на задания: {user_answers}
    
    Проверь каждый ответ. Сделай это строго и дружелюбно.
    
    ВАЖНО: Используй HTML-теги для форматирования, чтобы текст выглядел красиво в Telegram.
    Для правильных ответов пиши: ✅ <b>Правильно!</b>
    Для ошибок пиши: ❌ <b>Ошибка!</b> или ⚠️ <b>Почти правильно!</b>
    Объяснения выделяй обычным текстом.
    Правильные польские слова и предложения обязательно выделяй тегом <code>...</code>.
    """
    
    feedback = await get_ai_response(prompt)
    await message.answer(feedback, parse_mode="HTML")
    
    await state.clear()
    await message.answer("Отлично поработали! Напиши /lesson для следующего урока.")
