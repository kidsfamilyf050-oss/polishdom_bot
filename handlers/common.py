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
        "/remind — Напоминания\n"
        "/timezone — Сменить часовой пояс\n"
        "/setlevel — Сменить уровень вручную\n"
        "/profile — Мой профиль"
    )

@router.message(ProfileStates.waiting_for_name)
async def process_name(message: Message, state: FSMContext):
    await db.update_user_field(message.from_user.id, "name", message.text)
    await state.clear()
    await message.answer(f"Приятно познакомиться, {message.text}! Напиши /test, чтобы мы определили твой уровень.", reply_markup=ReplyKeyboardRemove())

@router.message(Command("timezone"))
async def cmd_timezone(message: Message):
    args = message.text.split()
    if len(args) < 2:
        return await message.answer(
            "Укажи свой часовой пояс в формате IANA.\n"
            "Например: `/timezone Asia/Almaty`\n"
            "Другие примеры: `Europe/Warsaw`, `Asia/Moscow`."
        )
    
    new_tz = args[1]
    try:
        # Проверяем, существует ли такой часовой пояс
        zoneinfo.ZoneInfo(new_tz)
    except Exception:
        return await message.answer(f"❌ Часовой пояс `{new_tz}` не найден. Попробуй другой.")
    
    await db.update_user_field(message.from_user.id, "timezone", new_tz)
    await message.answer(f"✅ Твой часовой пояс установлен: **{new_tz}**. Напоминания будут приходить по этому времени.", parse_mode="Markdown")

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
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

@router.callback_query(F.data.startswith("remind_"))
async def process_remind_time(callback: CallbackQuery):
    time_str = callback.data.split("_")[1]
    if time_str == "off":
        await db.update_user_field(callback.from_user.id, "reminder_time", None)
        await callback.message.edit_text("🔕 Напоминания отключены.")
    else:
        await db.update_user_field(callback.from_user.id, "reminder_time", time_str)
        await callback.message.edit_text(f"✅ Отлично! Я буду напоминать тебе каждый день в {time_str} по твоему местному времени.")
    await callback.answer()

@router.message(Command("setlevel"))
async def cmd_setlevel(message: Message):
    args = message.text.split()
    if len(args) < 2 or args[1] not in ["A0", "A1", "A2", "B1"]:
        return await message.answer("Напиши уровень, например: /setlevel A1 (доступно: A0, A1, A2, B1)")
    await db.update_user_field(message.from_user.id, "language_level", args[1])
    await message.answer(f"✅ Твой уровень изменен на {args[1]}.")
