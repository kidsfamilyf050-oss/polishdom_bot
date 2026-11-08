from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from db.mongo import db
import zoneinfo

router = Router()

class ProfileStates(StatesGroup):
    waiting_for_name = State()

# Веса для сортировки уровней в таблице лидеров
LEVEL_WEIGHTS = {"A0": 0, "A1": 1, "A2": 2, "B1": 3, "B2": 4, "C1": 5, "C2": 6}

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    user = await db.get_user(message.from_user.id)
    if not user:
        await db.create_user(message.from_user.id, message.from_user.username)
        user = await db.get_user(message.from_user.id)

    if not user.get("name"):
        await state.set_state(ProfileStates.waiting_for_name)
        await message.answer("👋 Привет! Я твой семейный репетитор польского. Как тебя зовут?")
        return

    await message.answer(
        f"👋 Привет, {user['name']}!\n"
        f"Твой уровень: {user.get('language_level', 'A0')}\n\n"
        "Команды:\n"
        "/test — Определить уровень\n"
        "/lesson — Начать урок\n"
        "/words — Мой словарь\n"
        "/top — Рейтинг семьи\n"
        "/remind — Напоминания\n"
        "/profile — Профиль"
    )

@router.message(ProfileStates.waiting_for_name)
async def process_name(message: Message, state: FSMContext):
    await db.update_user_field(message.from_user.id, "name", message.text)
    await state.clear()
    await message.answer(f"Приятно познакомиться, {message.text}! Напиши /test, чтобы мы определили твой уровень.", reply_markup=ReplyKeyboardRemove())

# --- НОВАЯ КОМАНДА: СЛОВАРЬ ---
@router.message(Command("words"))
async def cmd_words(message: Message):
    user = await db.get_user(message.from_user.id)
    if not user: return await message.answer("Напиши /start.")
    
    words = user.get("learned_words", [])
    if not words:
        return await message.answer("📚 Твой словарь пока пуст. Начни урок: /lesson")
    
    # Разбиваем слова по 5 штук в строке для красоты
    formatted_words = ""
    for i in range(0, len(words), 5):
        formatted_words += ", ".join(words[i:i+5]) + "\n"
        
    await message.answer(
        f"📚 <b>Твой словарь ({len(words)} слов):</b>\n\n"
        f"<i>{formatted_words}</i>",
        parse_mode="HTML"
    )

# --- НОВАЯ КОМАНДА: ТОП ---
@router.message(Command("top"))
async def cmd_top(message: Message):
    users = await db.get_all_users()
    
    # Фильтруем тех, кто прошел регистрацию (есть имя)
    active_users = [u for u in users if u.get("name")]
    
    if not active_users:
        return await message.answer("Пока нет активных учеников. Напишите /start.")

    # Сортируем: сначала по уровню, потом по идеальным сериям, потом по словам
    active_users.sort(
        key=lambda x: (
            LEVEL_WEIGHTS.get(x.get("language_level", "A0"), 0),
            x.get("perfect_streak", 0),
            len(x.get("learned_words", []))
        ),
        reverse=True
    )
    
    top_text = "🏆 <b>Рейтинг семьи:</b>\n\n"
    
    for i, u in enumerate(active_users[:10]): # Показываем топ-10
        name = u.get("name")
        lvl = u.get("language_level", "A0")
        words_count = len(u.get("learned_words", []))
        streak = u.get("perfect_streak", 0)
        
        if i == 0: medal = "🥇"
        elif i == 1: medal = "🥈"
        elif i == 2: medal = "🥉"
        else: medal = f"{i+1}."
        
        top_text += f"{medal} <b>{name}</b> — {lvl} (Слов: {words_count}, 🔥 {streak}/5)\n"
        
    await message.answer(top_text, parse_mode="HTML")

@router.message(Command("profile"))
async def cmd_profile(message: Message):
    user = await db.get_user(message.from_user.id)
    if not user: return await message.answer("Напиши /start.")
    await message.answer(
        f"👤 Имя: {user.get('name')}\n"
        f"📊 Уровень: {user.get('language_level')}\n"
        f"📚 Слов изучено: {len(user.get('learned_words', []))}\n"
        f"⏰ Напоминание: {user.get('reminder_time', 'Выключено')}"
    )

@router.message(Command("remind"))
async def cmd_remind(message: Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="09:00", callback_data="remind_09:00"),
            InlineKeyboardButton(text="12:00", callback_data="remind_12:00"),
            InlineKeyboardButton(text="15:00", callback_data="remind_15:00")
        ],
        [
            InlineKeyboardButton(text="18:00", callback_data="remind_18:00"),
            InlineKeyboardButton(text="20:00", callback_data="remind_20:00"),
            InlineKeyboardButton(text="21:00", callback_data="remind_21:00")
        ],
        [
            InlineKeyboardButton(text="22:00", callback_data="remind_22:00"),
            InlineKeyboardButton(text="❌ Отключить", callback_data="remind_off")
        ]
    ])
    await message.answer(
        "⏰ Выбери удобное время для ежедневных напоминаний.\n"
        "Время будет соответствовать твоему часовому поясу (по умолчанию `Asia/Almaty`).",
        reply_markup=keyboard
    )

@router.callback_query(F.data.startswith("remind_"))
async def process_remind_time(callback: CallbackQuery):
    time_str = callback.data.split("_")[1]
    if time_str == "off":
        await db.update_user_field(callback.from_user.id, "reminder_time", None)
        await callback.message.edit_text("🔕 Напоминания отключены.")
    else:
        await db.update_user_field(callback.from_user.id, "reminder_time", time_str)
        await callback.message.edit_text(f"✅ Отлично! Я буду напоминать тебе каждый день в {time_str}.")
    await callback.answer()

@router.message(Command("timezone"))
async def cmd_timezone(message: Message):
    args = message.text.split()
    if len(args) < 2:
        return await message.answer("Укажи пояс: `/timezone Asia/Almaty`")
    
    new_tz = args[1]
    try:
        zoneinfo.ZoneInfo(new_tz)
    except Exception:
        return await message.answer(f"❌ Часовой пояс `{new_tz}` не найден.")
    
    await db.update_user_field(message.from_user.id, "timezone", new_tz)
    await message.answer(f"✅ Твой часовой пояс установлен: <b>{new_tz}</b>.", parse_mode="HTML")

@router.message(Command("setlevel"))
async def cmd_setlevel(message: Message):
    args = message.text.split()
    if len(args) < 2 or args[1] not in ["A0", "A1", "A2", "B1", "B2", "C1", "C2"]:
        return await message.answer("Напиши уровень, например: /setlevel A1")
    await db.update_user_field(message.from_user.id, "language_level", args[1])
    await message.answer(f"✅ Твой уровень изменен на {args[1]}.")
