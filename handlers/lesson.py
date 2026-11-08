import os, uuid, json, asyncio, logging
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

LESSON_SYSTEM_PROMPT = "Ты репетитор польского. Верни ТОЛЬКО валидный JSON, без markdown и объяснений."
CHECK_SYSTEM_PROMPT  = "Ты строгий экзаменатор польского. Верни ТОЛЬКО валидный JSON, без markdown и объяснений."

def _strip_tags(s: str) -> str:
    for t in ("<b>", "</b>", "<i>", "</i>", "<code>", "</code>", "<pre>", "</pre>"):
        s = s.replace(t, "")
    return s

def _parse_json(raw: str):
    if not raw or raw.startswith("⚠️") or raw.startswith("Ошибка"):
        return None
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`").strip()
        if raw.startswith("json"):
            raw = raw[4:].strip()
    return json.loads(raw)

async def _tts(text, path) -> bool:
    try:
        await asyncio.to_thread(gTTS(text=text, lang="pl").save, path)
        return True
    except Exception as e:
        logger.error(f"gTTS: {e}")
        return False

def _lesson_html(l: dict) -> str:
    out = ["<b>📚 Новый урок</b>\n", "<b>🆕 Новые слова:</b>"]
    for i, w in enumerate(l.get("words", []), 1):
        out.append(f"{i}. <b>{w['pl']}</b> — {w['ru']}\n   <i>{w['example_pl']}</i> — {w['example_ru']}")
    g = l.get("grammar") or {}
    if g:
        out.append(f"\n<b>📖 {g.get('title','')}</b>\n{g.get('explanation','')}")
    out.append("\n<b>💬 Диалог:</b>")
    for ln in l.get("dialogue", []):
        out.append(f"<b>{ln['speaker']}:</b> {ln['pl']}\n<i>({ln['ru']})</i>")
    out.append("\n<b>📝 Задания:</b>")
    for i, t in enumerate(l.get("tasks", []), 1):
        out.append(f"{i}. {t['ru']}")
    return "\n".join(out)

def _feedback_html(fb: dict, correct: int, total: int, streak: int, leveled_to: str | None) -> str:
    out = []
    for r in fb.get("results", []):
        icon = "✅" if r.get("is_correct") else "❌"
        out.append(f"{icon} <b>Задание {r.get('index')}:</b>")
        out.append(f"  Твой ответ: {r.get('user_answer')}")
        out.append(f"  Правильно: <code>{r.get('correct_answer')}</code>")
        if r.get("explanation"):
            out.append(f"  💡 {r['explanation']}")
    if fb.get("overall"):
        out.append(f"\n<b>💬 Комментарий:</b> {fb['overall']}")
    out.append(f"\n📊 Результат: {correct}/{total}")
    out.append(f"🔥 Серия идеальных уроков: {streak}/5")
    if leveled_to:
        out.append(f"\n🎉🎉 <b>Поздравляю! Новый уровень: {leveled_to}!</b>")
    return "\n".join(out)

@router.message(Command("lesson"))
async def cmd_lesson(message: Message, state: FSMContext):
    if await state.get_state() == LessonStates.waiting_for_answers.state:
        return await message.answer("⚠️ У тебя уже есть активный урок. Ответь на задания или /cancel.")
    user = await db.get_user(message.from_user.id)
    if not user:
        return await message.answer("Сначала напиши /start.")
    level = user.get("language_level", "A0")
    name = user.get("name") or "друг"
    syl = get_syllabus(level)

    review = await db.get_words_for_review(message.from_user.id, limit=5)
    review_block = ""
    if review:
        lines = "\n".join(f"- {w['word']} — {w['translation']}" for w in review)
        review_block = f"\n\nВключи в урок слова на повторение:\n{lines}"

    await message.answer(f"🔄 {name}, готовлю урок для уровня {level}...")

    prompt = f"""Составь урок польского для уровня {level}.

ТЕМЫ УРОВНЯ: {', '.join(syl['topics'])}
ГРАММАТИКА УРОВНЯ: {', '.join(syl['grammar'])}

ТРЕБОВАНИЯ:
- 5 новых слов строго по темам уровня.
- 1 правило грамматики с 2 примерами.
- Диалог 3–4 реплики, простой.
- Ровно 3 задания на перевод с русского на польский.{review_block}

Верни ТОЛЬКО JSON:
{{
  "words": [{{"pl":"...","ru":"...","example_pl":"...","example_ru":"..."}}],
  "grammar": {{"title":"...","explanation":"...","examples":["..."]}},
  "dialogue": [{{"speaker":"A","pl":"...","ru":"..."}}],
  "tasks": [{{"ru":"...","correct":"..."}}]
}}"""

    raw = await get_ai_response(prompt, LESSON_SYSTEM_PROMPT)
    try:
        lesson = _parse_json(raw)
    except Exception as e:
        logger.error(f"Lesson JSON error: {e}")
        lesson = None
    if not lesson or "words" not in lesson or "tasks" not in lesson:
        return await message.answer("😔 Не удалось сгенерировать урок. Попробуй ещё раз.")

    try:
        await db.add_learned_words(
            message.from_user.id,
            [{"word": w["pl"], "translation": w["ru"], "level": level} for w in lesson["words"]],
        )
    except Exception as e:
        logger.error(f"Save words: {e}")

    html = _lesson_html(lesson)
    try:
        await message.answer(html, parse_mode="HTML")
    except Exception:
        await message.answer(_strip_tags(html))

    dialogue = " ".join(x["pl"] for x in lesson.get("dialogue", []))
    if dialogue:
        path = f"audio_{uuid.uuid4().hex}.mp3"
        if await _tts(dialogue, path):
            try:
                await message.answer_voice(FSInputFile(path), caption="🔊 Диалог урока")
            finally:
                try: os.remove(path)
                except OSError: pass
        else:
            await message.answer("⚠️ Аудио временно недоступно.")

    await state.set_state(LessonStates.waiting_for_answers)
    await state.update_data(lesson=lesson, level_at_start=level)
    await message.answer("📝 Напиши ответы на 3 задания через точку с запятой (;).")

@router.message(LessonStates.waiting_for_answers, ~F.text.startswith("/"))
async def check_lesson(message: Message, state: FSMContext):
    data = await state.get_data()
    lesson = data.get("lesson")
    level_at_start = data.get("level_at_start", "A0")
    if not lesson:
        await state.clear()
        return await message.answer("Урок потерян. Начни заново: /lesson")

    tasks = lesson.get("tasks", [])
    await message.answer("🔄 Проверяю ответы...")

    prompt = f"""Проверь ответы ученика уровня {level_at_start}.

Задания и правильные ответы:
{json.dumps(tasks, ensure_ascii=False)}

Ответы ученика (через ';'): {message.text}

Сопоставь по порядку. Если ответов меньше — оставь соответствующие пустыми и is_correct=false.
Правильным считай только грамматически верный ответ (мелкие опечатки допустимы).

Верни ТОЛЬКО JSON:
{{
  "results": [{{"index":1,"user_answer":"...","correct_answer":"...","is_correct":true,"explanation":"..."}}],
  "total_correct": 0,
  "overall": "..."
}}"""

    raw = await get_ai_response(prompt, CHECK_SYSTEM_PROMPT)
    try:
        fb = _parse_json(raw)
    except Exception as e:
        logger.error(f"Check JSON error: {e}")
        fb = None
    if not fb:
        await state.clear()
        return await message.answer("⚠️ Не удалось проверить ответы. Начни новый урок: /lesson")

    total = len(tasks)
    correct = sum(1 for r in fb.get("results", []) if r.get("is_correct"))
    all_correct = total > 0 and correct == total

    await db.update_progress(message.from_user.id, all_correct)
    user = await db.get_user(message.from_user.id)
    prog = (user or {}).get("progress", {})
    streak = prog.get("streak", 0)
    leveled_to = None

    if streak >= 5:
        nl = next_level(level_at_start)
        if nl:
            await db.update_user_field(message.from_user.id, "language_level", nl)
            prog["streak"] = 0
            await db.update_user_field(message.from_user.id, "progress", prog)
            leveled_to = nl
            streak = 0

    try:
        for w in lesson.get("words", []):
            await db.update_word_after_review(message.from_user.id, w["pl"], all_correct)
    except Exception as e:
        logger.error(f"SRS update: {e}")

    html = _feedback_html(fb, correct, total, streak, leveled_to)
    try:
        await message.answer(html, parse_mode="HTML")
    except Exception:
        await message.answer(_strip_tags(html))

    await state.clear()
    await message.answer("Отлично! /lesson — следующий урок, /words — мои слова.")
