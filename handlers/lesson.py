import os
import re
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
from syllabus import get_syllabus, next_level

router = Router()
logger = logging.getLogger(__name__)


class LessonStates(StatesGroup):
    waiting_for_answers = State()


# Системные промпты для урока и проверки
LESSON_SYSTEM_PROMPT = (
    "Ты — строгий учитель польского языка. Составляешь уроки строго по учебному "
    "плану и не выходишь за рамки уровня ученика."
)

CHECK_SYSTEM_PROMPT = (
    "Ты — строгий учитель польского. Проверяешь ответы ученика, указываешь "
    "ошибки и объясняешь их по-русски."
)


# ---------- вспомогательные функции ----------

async def generate_audio(text: str, filename: str) -> bool:
    try:
        tts = gTTS(text=text, lang="pl", slow=False)
        await asyncio.to_thread(tts.save, filename)
        return True
    except Exception as e:
        logger.error(f"Ошибка gTTS: {e}")
        return False


def _pick_topic(level: str, lessons_completed: int) -> str:
    """Выбирает тему по кругу в зависимости от числа пройденных уроков."""
    syl = get_syllabus(level)
    topics = syl.get("topics") or ["общая тема"]
    return topics[lessons_completed % len(topics)]


def _extract_words(text: str):
    """Достаёт список слов из скрытого блока [[WORDS]]."""
    idx = text.find("[[WORDS]]")
    if idx == -1:
        return []
    block = text[idx + len("[[WORDS]]"):]
    words = []
    for line in block.splitlines():
        line = line.strip()
        if not line or "|" not in line:
            continue
        pl = line.split("|", 1)[0].strip()
        # убираем возможные нумерации вроде "1. ", "1) ", "- "
        pl = re.sub(r"^[\d\.\)\-\s]+", "", pl).strip()
        if pl and pl not in words:
            words.append(pl)
    return words[:5]


def _strip_words_block(text: str) -> str:
    """Убирает блок [[WORDS]] и всё после него из текста урока."""
    idx = text.find("[[WORDS]]")
    if idx == -1:
        return text
    return text[:idx].rstrip()


def _strip_perfect_marker(text: str) -> str:
    return text.replace("[PERFECT]", "").rstrip()


# ---------- команда /lesson ----------

@router.message(Command("lesson"))
async def cmd_lesson(message: Message, state: FSMContext):
    if await state.get_state() == LessonStates.waiting_for_answers.state:
        await message.answer(
            "У тебя уже есть активный урок. Ответь на задания или дождись проверки."
        )
        return

    user = await db.get_user(message.from_user.id)
    if not user:
        await message.answer("Сначала напиши /start.")
        return

    level = user.get("language_level", "A0")
    name = user.get("name") or "друг"
    lessons_completed = user.get("lessons_completed", 0) or 0
    learned_words = user.get("learned_words", []) or []

    syl = get_syllabus(level)
    topic = _pick_topic(level, lessons_completed)
    grammar = ", ".join(syl.get("grammar") or [])

    # 5 последних изученных слов → в промпт на повторение
    review_words = learned_words[-5:] if learned_words else []
    review_block = ""
    if review_words:
        review_block = (
            "Обязательно включи в урок эти ранее изученные слова для повторения: "
            + ", ".join(review_words)
            + "."
        )

    await message.answer(
        f"🔄 {name}, готовлю урок: уровень {level}, тема «{topic}»..."
    )

    prompt = f"""Ты — строгий учитель польского языка. Ученик уровня {level}.
Тема урока: {topic}.
Грамматика уровня: {grammar}.

Составь урок СТРОГО по теме «{topic}» и строго по уровню {level}.
Не выходи за рамки уровня и темы.

Структура:
1. 5 новых слов по теме «{topic}» — слово, перевод, пример и перевод примера.
2. Правило грамматики ({grammar}) — кратко, с 1-2 примерами.
3. Короткий диалог (3-4 реплики) с переводом на русский.
4. Ровно 3 задания на перевод с русского на польский.

{review_block}

В САМОМ КОНЦЕ ответа добавь служебный блок строго в таком виде
(без тегов, без markdown, без звёздочек):

[[WORDS]]
польское_слово|русский_перевод
польское_слово|русский_перевод
польское_слово|русский_перевод
польское_слово|русский_перевод
польское_слово|русский_перевод

ВАЖНО: Используй в тексте только теги <b> и <code>. Обязательно закрывай их!
"""

    lesson_raw = await get_ai_response(prompt, LESSON_SYSTEM_PROMPT)

    if not lesson_raw or lesson_raw.startswith("⚠️") or lesson_raw.startswith("Ошибка"):
        await message.answer("⚠️ Не удалось получить урок от ИИ. Попробуй ещё раз через минуту.")
        return

    # сохраняем новые слова
    new_words = _extract_words(lesson_raw)
    if new_words:
        try:
            await db.add_learned_words(message.from_user.id, new_words)
        except Exception as e:
            logger.error(f"Не удалось сохранить слова: {e}")

    lesson_text = _strip_words_block(lesson_raw)

    # отправляем сам урок
    try:
        await message.answer(lesson_text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Ошибка HTML в уроке: {e}. Отправляю текстом.")
        await message.answer(lesson_text)

    # озвучка (первые 300 символов без тегов)
    text_to_speak = re.sub(r"<[^>]+>", "", lesson_text)[:300]
    if text_to_speak.strip():
        filename = f"audio_{uuid.uuid4().hex}.mp3"
        if await generate_audio(text_to_speak, filename):
            try:
                await message.answer_voice(
                    FSInputFile(filename), caption="🔊 Послушай урок (озвучка Google)"
                )
            finally:
                try:
                    os.remove(filename)
                except OSError:
                    pass
        else:
            await message.answer("⚠️ Аудио временно недоступно.")

    await state.set_state(LessonStates.waiting_for_answers)
    await state.update_data(lesson_text=lesson_text, level_at_start=level)
    await message.answer("📝 Напиши ответы на 3 задания через точку с запятой (;).")


# ---------- проверка ответов ----------

@router.message(LessonStates.waiting_for_answers)
async def check_lesson(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("Пожалуйста, напиши ответы текстом.")
        return

    data = await state.get_data()
    lesson_text = data.get("lesson_text")
    level_at_start = data.get("level_at_start", "A0")
    user_answers = message.text

    if not lesson_text:
        await state.clear()
        await message.answer("Урок потерян. Начни заново: /lesson")
        return

    await message.answer(
        "🔄 Принял ответы! Анализирую ошибки и готовлю разбор... Подожди 10-15 секунд."
    )

    prompt = f"""Вот текст урока, который ты составил ранее для ученика уровня {level_at_start}:

{lesson_text}

Ученик прислал ответы на 3 задания:
{user_answers}

Проверь каждый ответ строго и дружелюбно.
- Для правильного ответа пиши: ✅ <b>Правильно!</b>
- Для ошибки пиши: ❌ <b>Ошибка!</b> или ⚠️ <b>Почти правильно!</b>
- Правильные польские слова обязательно выделяй тегом <code>...</code>.
- В конце разбора кратко объясни каждую ошибку по-русски.

ВАЖНО: в самом конце ответа, на отдельной строке, добавь скрытую служебную метку:
- Если ВСЕ 3 ответа абсолютно правильные (0 ошибок) — напиши на новой строке: [PERFECT]
- Если есть хотя бы одна ошибка — НЕ пиши [PERFECT].
"""

    feedback_raw = await get_ai_response(prompt, CHECK_SYSTEM_PROMPT)

    if not feedback_raw or feedback_raw.startswith("⚠️") or feedback_raw.startswith("Ошибка"):
        await state.clear()
        await message.answer("⚠️ Не удалось проверить ответы. Попробуй начать новый урок: /lesson")
        return

    is_perfect = "[PERFECT]" in feedback_raw
    feedback_text = _strip_perfect_marker(feedback_raw)

    try:
        await message.answer(feedback_text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Ошибка HTML в проверке: {e}. Отправляю текстом.")
        await message.answer(feedback_text)

    # обновляем счётчики
    try:
        await db.increment_field(message.from_user.id, "lessons_completed", 1)
        if is_perfect:
            await db.increment_field(message.from_user.id, "perfect_streak", 1)
        else:
            await db.reset_field(message.from_user.id, "perfect_streak", 0)
    except Exception as e:
        logger.error(f"Не удалось обновить счётчики: {e}")

    user = await db.get_user(message.from_user.id)
    streak = (user or {}).get("perfect_streak", 0) or 0

    if is_perfect:
        await message.answer(
            f"🔥 Отличный урок без ошибок! Серия идеальных уроков: {streak}/5."
        )
    else:
        await message.answer(
            "📖 Есть ошибки — серия идеальных уроков сброшена. Тренируйся дальше!"
        )

    # повышение уровня при 5 идеальных подряд
    if streak >= 5:
        new_level = next_level(level_at_start)
        if new_level:
            await db.update_user_field(message.from_user.id, "language_level", new_level)
            await db.reset_field(message.from_user.id, "perfect_streak", 0)
            await message.answer(
                f"🎉🎉 Поздравляю! Пять идеальных уроков подряд.\n"
                f"Твой новый уровень: {new_level}!\n"
                f"Продолжай в том же духе: /lesson"
            )
        else:
            await db.reset_field(message.from_user.id, "perfect_streak", 0)
            await message.answer(
                "🏆 Ты уже на максимальном уровне C2! Продолжай совершенствоваться — /lesson."
            )

    await state.clear()
    await message.answer("Готов к следующему уроку? Напиши /lesson.")
