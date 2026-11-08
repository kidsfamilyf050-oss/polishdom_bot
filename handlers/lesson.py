import os, uuid, edge_tts
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

@router.message(Command("lesson"))
async def cmd_lesson(message: Message, state: FSMContext):
    user = await db.get_user(message.from_user.id)
    level = user.get("language_level", "A0")
    name = user.get("name", "друг")
    
    await message.answer(f"🔄 {name}, готовлю урок для уровня {level}...")
    
    # Просим нейросеть использовать HTML для красивого форматирования
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
    
    # Отправляем урок с включенным HTML-форматированием
    await message.answer(lesson_text, parse_mode="HTML")
    
    # Генерируем аудио
    audio_text = "Урок польского. Слушай внимательно."
    
    filename = f"audio_{uuid.uuid4().hex}.mp3"
    voice = os.getenv("EDGE_TTS_VOICE", "pl-PL-MarekNeural")
    communicate = edge_tts.Communicate(audio_text, voice)
    await communicate.save(filename)
    
    await message.answer_voice(FSInputFile(filename), caption="🔊 Аудио к уроку")
    os.remove(filename)
    
    await state.set_state(LessonStates.waiting_for_answers)
    await state.update_data(current_lesson=lesson_text)
    await message.answer("📝 Напиши ответы на 3 задания через точку с запятой (;).")

@router.message(LessonStates.waiting_for_answers)
async def check_lesson(message: Message, state: FSMContext):
    data = await state.get_data()
    lesson_text = data.get("current_lesson")
    user_answers = message.text
    
    await message.answer("🔄 Проверяю твои ответы...")
    
    # Просим нейросеть сделать красивый и четкий разбор
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
    
    # Отправляем проверку с включенным HTML-форматированием
    await message.answer(feedback, parse_mode="HTML")
    
    await state.clear()
    await message.answer("Отлично поработали! Напиши /lesson для следующего урока.")
