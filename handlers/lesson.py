import os
import re
import asyncio
import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from ai.openrouter import get_ai_response
from db.mongo import db
from syllabus import get_syllabus, next_level

router = Router()
logger = logging.getLogger(__name__)

class LessonStates(StatesGroup):
    waiting_for_answers = State()

LESSON_SYSTEM_PROMPT = "Ты — строгий учитель польского языка. Составляешь уроки строго по учебному плану и не выходишь за рамки уровня ученика."
CHECK_SYSTEM_PROMPT = "Ты — строгий учитель польского. Проверяешь ответы ученика, указываешь ошибки и объясняешь их по-русски."

def _pick_topic(level: str, lessons_completed: int) -> str:
    syl = get_syllabus(level)
    topics = syl.get("topics") or ["общая тема"]
    return topics[lessons_completed % len(topics)]

def _extract_words(text: str):
    idx = text.find("[[WORDS]]")
    if idx == -1: return []
    block = text[idx + len("[[WORDS]]"):]
    words = []
    for line in block.splitlines():
        line = line.strip()
        if not line or "|" not in line: continue
        pl = line.split("|", 1)[0].strip()
        pl = re.sub(r"^[\d\.\)\-\s]+", "", pl).strip()
        if pl and pl not in words: words.append(pl)
    return words[:5]

def _strip_words_block(text: str) -> str:
    idx = text.find("[[WORDS]]")
    return text[:idx].rstrip() if idx != -1 else text

def _strip_perfect_marker(text: str) -> str:
    return text.replace("[PERFECT]", "").rstrip()

def _clean_html(text: str) -> str:
    """Убирает теги, если их не понимает Telegram."""
    # Заменяем жирный шрифт на обычный
    text = text.replace("<b>", "").replace("</b>", "")
    text = text.replace("<i>", "").replace("</i>", "")
    # Убираем любые другие теги вроде <student>
    text = re.sub(r'<[^>]+>', '', text)
    return text

@router.message(Command("lesson"))
async def cmd_lesson(message: Message, state: FSMContext):
    if await state.get_state() == LessonStates.waiting_for_answers.state:
        await message.answer("У тебя уже есть активный урок. Ответь на задания.")
        return

    user = await db.get_user(message.from_user.id)
    if not user: return await message.answer("Сначала напиши /start.")

    level = user.get("language_level", "A0")
    name = user.get("name") or "друг"
    lessons_completed = user.get("lessons_completed", 0) or 0
    learned_words = user.get("learned_words", []) or []

    syl = get_syllabus(level)
    topic = _pick_topic(level, lessons_completed)
    grammar = ", ".join(syl.get("grammar") or [])

    review_words = learned_words[-5:] if learned_words else []
    review_block = f"Обязательно включи в урок эти ранее изученные слова для повторения: {', '.join(review_words)}." if review_words else ""

    await message.answer(f"🔄 {name}, готовлю урок: уровень {level}, тема «{topic}»...")

    prompt = f"""Ты — строгий учитель польского языка. Ученик уровня {level}.
Тема урока: {topic}.
Грамматика уровня: {grammar}.

Составь урок СТРОГО по теме «{topic}» и строго по уровню {level}.
Структура:
1. 5 новых слов по теме «{topic}» — слово, перевод, пример и перевод примера.
2. Правило грамматики ({grammar}) — кратко, с 1-2 примерами.
3. Короткий диалог (3-4 реплики) с переводом на русский. (Пиши диалог через тире, БЕЗ тегов <student> и <teacher>!)
4. Ровно 3 задания на перевод с русского на польский.

{review_block}

В САМОМ КОНЦЕ ответа добавь служебный блок строго в таком виде:
[[WORDS]]
польское_слово|русский_перевод
польское_слово|русский_перевод
польское_слово|русский_перевод
польское_слово|русский_перевод
польское_слово|русский_перевод

ВАЖНО: Используй в тексте ТОЛЬКО теги <b> и <i> (для жирного и курсива). 
НИКОГДА не используй теги вроде <student>, <teacher>, <speaker> и т.д.!
"""

    lesson_raw = await get_ai_response(prompt, LESSON_SYSTEM_PROMPT)

    if not lesson_raw or lesson_raw.startswith("⚠️") or lesson_raw.startswith("Ошибка"):
        await message.answer(f"⚠️ Ошибка от ИИ:\n<code>{lesson_raw}</code>", parse_mode="HTML")
        return

    new_words = _extract_words(lesson_raw)
    if new_words:
        await db.add_learned_words(message.from_user.id, new_words)

    lesson_text = _strip_words_block(lesson_raw)

    try:
        await message.answer(lesson_text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Ошибка HTML в уроке: {e}")
        clean_text = _clean_html(lesson_text)
        await message.answer(clean_text)

    await state.set_state(LessonStates.waiting_for_answers)
    await state.update_data(lesson_text=lesson_text, level_at_start=level)
    await message.answer("📝 Напиши ответы на 3 задания через точку с запятой (;).")

@router.message(LessonStates.waiting_for_answers)
async def check_lesson(message: Message, state: FSMContext):
    if not message.text:
        return await message.answer("Пожалуйста, напиши ответы текстом.")

    data = await state.get_data()
    lesson_text = data.get("lesson_text")
    level_at_start = data.get("level_at_start", "A0")
    user_answers = message.text

    if not lesson_text:
        await state.clear()
        return await message.answer("Урок потерян. Начни заново: /lesson")

    await message.answer("🔄 Проверяю ответы... Подожди 10-15 секунд.")

    prompt = f"""Вот текст урока для ученика уровня {level_at_start}:
{lesson_text}

Ученик прислал ответы:
{user_answers}

Проверь каждый ответ строго.
- Для правильного ответа пиши: ✅ <b>Правильно!</b>
- Для ошибки пиши: ❌ <b>Ошибка!</b> или ⚠️ <b>Почти правильно!</b>
- Правильные польские слова выделяй тегом <b>...</b> (жирным).
- В конце разбора кратко объясни ошибки по-русски.

ВАЖНО: Используй ТОЛЬКО теги <b> и <i>. Не придумывай другие теги!
В самом конце ответа на новой строке добавь метку:
- Если ВСЕ 3 ответа абсолютно правильные: [PERFECT]
- Если есть хоть одна ошибка: НЕ пиши [PERFECT]."""

    feedback_raw = await get_ai_response(prompt, CHECK_SYSTEM_PROMPT)

    if not feedback_raw or feedback_raw.startswith("⚠️") or feedback_raw.startswith("Ошибка"):
        await state.clear()
        await message.answer(f"⚠️ Ошибка проверки от ИИ:\n<code>{feedback_raw}</code>", parse_mode="HTML")
        return

    is_perfect = "[PERFECT]" in feedback_raw
    feedback_text = _strip_perfect_marker(feedback_raw)

    try:
        await message.answer(feedback_text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Ошибка HTML в проверке: {e}")
        clean_text = _clean_html(feedback_text)
        await message.answer(clean_text)

    await db.increment_field(message.from_user.id, "lessons_completed", 1)
    if is_perfect:
        await db.increment_field(message.from_user.id, "perfect_streak", 1)
    else:
        await db.reset_field(message.from_user.id, "perfect_streak", 0)

    user = await db.get_user(message.from_user.id)
    streak = (user or {}).get("perfect_streak", 0) or 0

    if is_perfect:
        await message.answer(f"🔥 Отличный урок без ошибок! Серия идеальных уроков: {streak}/5.")
    else:
        await message.answer("📖 Есть ошибки — серия идеальных уроков сброшена. Тренируйся дальше!")

    if streak >= 5:
        new_level = next_level(level_at_start)
        if new_level:
            await db.update_user_field(message.from_user.id, "language_level", new_level)
            await db.reset_field(message.from_user.id, "perfect_streak", 0)
            await message.answer(f"🎉🎉 Поздравляю! Пять идеальных уроков подряд.\nТвой новый уровень: {new_level}!\nПродолжай: /lesson")
        else:
            await db.reset_field(message.from_user.id, "perfect_streak", 0)
            await message.answer("🏆 Ты уже на максимальном уровне C2!")

    await state.clear()
    await message.answer("Готов к следующему уроку? Напиши /lesson.")
