from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from db.mongo import db

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
        "/remind 21:00 — Напоминание\n"
        "/profile — Мой профиль"
    )

@router.message(ProfileStates.waiting_for_name)
async def process_name(message: Message, state: FSMContext):
    await db.update_user_field(message.from_user.id, "name", message.text)
    await state.clear()
    await message.answer(f"Приятно познакомиться, {message.text}! Напиши /test, чтобы мы определили твой уровень.", reply_markup=ReplyKeyboardRemove())

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
    args = message.text.split()
    if len(args) < 2:
        return await message.answer("Формат: /remind 21:00")
    await db.update_user_field(message.from_user.id, "reminder_time", args[1])
    await message.answer(f"✅ Буду напоминать каждый день в {args[1]}.")
