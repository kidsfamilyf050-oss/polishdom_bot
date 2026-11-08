import re
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from ai.openrouter import get_ai_response, TEST_SYSTEM_PROMPT
from db.mongo import db

router = Router()

class TestStates(StatesGroup):
    q1 = State()
    q2 = State()
    q3 = State()

@router.message(Command("test"))
async def start_test(message: Message, state: FSMContext):
    await state.set_state(TestStates.q1)
    await message.answer("📝 Диагностика. Вопрос 1: Переведи на польский: «У меня есть жена и двое детей». (Если не знаешь — напиши по-русски).")

@router.message(TestStates.q1)
async def test_q1(message: Message, state: FSMContext):
    await state.update_data(ans1=message.text)
    await state.set_state(TestStates.q2)
    await message.answer("Вопрос 2: Переведи на польский: «Мы живем в Казахстане».")

@router.message(TestStates.q2)
async def test_q2(message: Message, state: FSMContext):
    await state.update_data(ans2=message.text)
    await state.set_state(TestStates.q3)
    await message.answer("Вопрос 3: Как сказать «Я работаю, а жена отдыхает»?")

@router.message(TestStates.q3)
async def test_q3(message: Message, state: FSMContext):
    await state.update_data(ans3=message.text)
    data = await state.get_data()
    await state.clear()
    
    await message.answer("🔄 Анализирую ответы...")
    
    prompt = f"""
    Оцени уровень польского (A0, A1, A2, B1...).
    Ответ 1: {data['ans1']}
    Ответ 2: {data['ans2']}
    Ответ 3: {data['ans3']}
    Если ответы написаны на русском (кириллицей) — ставь строго A0.
    Выведи только код уровня (например, A1).
    """
    
    result = await get_ai_response(prompt, TEST_SYSTEM_PROMPT)
    match = re.search(r'(A[0-2]|B1|B2|C1|C2)', result)
    level = match.group(0) if match else "A0"
    
    await db.update_user_field(message.from_user.id, "language_level", level)
    await message.answer(f"Твой уровень: {level}.\nТеперь напиши /lesson, чтобы начать обучение!")
