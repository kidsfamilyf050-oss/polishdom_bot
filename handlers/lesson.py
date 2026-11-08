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
    
    prompt = f"""
    Ты — опытный репетитор польского. Составь мини-урок для ученика уровня {level}.
    Структура:
    1. 5 новых слов с переводом.
    2. 1 правило грамматики (кратко).
    3. Короткий диалог (3-4 реплики) с переводом.
    4. 3 задания (перевод с русского на польский).
    Форматируй текст красиво с эмодзи. Не пиши лишнего.
    """
    
    lesson_text = await get_ai_response(prompt)
    
    await message.answer(lesson_text)
    
    # Генерируем аудио для диалога (вырезаем примерный текст диалога)
    # Для простоты озвучим просто 3 случайных польских слова из ответа
    # В идеале нужно просить ИИ отдать диалог отдельным блоком, но пока так:
    
    audio_text = f"Урок польского. Уровень {level}. Слушай внимательно."
    
    filename = f"audio_{uuid.uuid4().hex}.mp3"
    voice = os.getenv("EDGE_TTS_VOICE", "pl-PL-MarekNeural")
    communicate = edge_tts.Communicate(audio_text, voice) # Тут можно передать текст диалога
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
    
    prompt = f"""
    Вот текст урока:
    {lesson_text}
    
    Ученик прислал ответы на задания: {user_answers}
    
    Проверь каждый ответ. Укажи, где ошибка, объясни правило и дай правильный вариант.
    Будь строгим, но дружелюбным. Как в примерах: "Ошибка №1... Правильно...".
    """
    
    feedback = await get_ai_response(prompt)
    await message.answer(feedback)
    
    await state.clear()
    await message.answer("Отлично поработали! Напиши /lesson для следующего урока.")
