import os
import uuid
import asyncio
import logging
from gtts import gTTS
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from ai.openrouter import get_ai_response
from db.mongo import db

router = Router()
logger = logging.getLogger(__name__)

class LessonStates(StatesGroup):
    waiting_for_answers = State()

async def generate_audio(text: str, filename: str) -> bool:
    """Генерирует аудио с помощью gTTS (Google Text-to-Speech)."""
    try:
        # Создаем объект gTTS для польского языка
        tts = gTTS(text=text, lang='pl', slow=False)
        # Сохраняем в файл. Используем to_thread, чтобы не блокировать бота
        await asyncio.to_thread(tts.save, filename)
        return True
    except Exception as e:
        logger.error(f"Ошибка gTTS: {e}")
        return False

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
    
    ВАЖНО: Используй ТОЛЬКО теги <b> и <code>. Обязательно закрывай их! (например, <b>Текст</b>).
    """
    
    lesson_text = await get_ai_response(prompt)
    
    try:
        await message.answer(lesson_text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Ошибка HTML в уроке: {e}. Отправляю текстом.")
        await message.answer(lesson_text)
    
    # Генерируем аудио из первых 300 символов урока (чтобы файл не был слишком тяжелым)
    # В идеале тут должен быть выделенный диалог, но для теста возьмем кусок текста
    text_to_speak = lesson_text.replace('<b>', '').replace('</b>', '').replace('<code>', '').replace('</code>', '')[:300]
    
    filename = f"audio_{uuid.uuid4().hex}.mp3"
    success = await generate_audio(text_to_speak, filename)
    
    if success:
        await message.answer_voice(FSInputFile(filename), caption="🔊 Послушай урок (озвучка Google)")
        os.remove(filename)
    else:
        await message.answer("⚠️ Аудио временно недоступно.")
    
    await state.set_state(LessonStates.waiting_for_answers)
    await state.update_data(current_lesson=lesson_text)
    await message.answer("📝 Напиши ответы на 3 задания через точку с запятой (;).")

@router.message(LessonStates.waiting_for_answers)
async def check_lesson(message: Message, state: FSMContext):
    data = await state.get_data()
    lesson_text = data.get("current_lesson")
    user_answers = message.text
    
    await message.answer("🔄 Принял ответы! Анализирую ошибки и готовлю разбор... Подожди 10-15 секунд.")
    
    prompt = f"""
    Вот текст урока:
    {lesson_text}
    
    Ученик прислал ответы: {user_answers}
    
    Проверь каждый ответ. Сделай это строго и дружелюбно.
    Для правильных ответов пиши: ✅ <b>Правильно!</b>
    Для ошибок пиши: ❌ <b>Ошибка!</b> или ⚠️ <b>Почти правильно!</b>
    Правильные польские слова обязательно выделяй тегом <code>...</code>.
    """
    
    try:
        feedback = await get_ai_response(prompt)
        
        try:
            await message.answer(feedback, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Ошибка HTML в проверке: {e}. Отправляю текстом.")
            await message.answer(feedback)
            
        await state.clear()
        await message.answer("Отлично поработали! Напиши /lesson для следующего урока.")
        
    except Exception as e:
        logger.error(f"Критическая ошибка при проверке: {e}")
        await message.answer("⚠️ Произошла ошибка при проверке. Попробуй написать ответы еще раз или начни новый урок через /lesson.")
        await state.clear()
