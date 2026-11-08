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
    await message.answer("Вопрос 2: Переведи на польский: «Вчера мы жили в Казахстане, а завтра поедем в Польшу».") # Добавили прошедшее и будущее время

@router.message(TestStates.q2)
async def test_q2(message: Message, state: FSMContext):
    await state.update_data(ans2=message.text)
    await state.set_state(TestStates.q3)
    await message.answer("Вопрос 3: Как сказать «Я работаю, а жена отдыхает, потому что она устала»?") # Добавили сложное предложение

@router.message(TestStates.q3)
async def test_q3(message: Message, state: FSMContext):
    await state.update_data(ans3=message.text)
    data = await state.get_data()
    await state.clear()
    
    await message.answer("🔄 Анализирую ответы...")
    
    # ЖЕСТКИЙ ПРОМПТ
    prompt = f"""
    Ты — строгий экзаменатор по польскому языку. Оцени уровень (A0, A1, A2, B1).
    Ответ 1: {data['ans1']}
    Ответ 2: {data['ans2']}
    Ответ 3: {data['ans3']}
    
    ПРАВИЛА ОЦЕНКИ:
    - Если ответы на русском (кириллицей) или это просто набор слов — ставь A0.
    - Если ученик использует ТОЛЬКО настоящее время (mam, mieszkam, pracuję) и простые предложения — ставь СТРОГО A1.
    - Если ученик правильно использовал прошедшее время (mieszkałem) и будущее (będę), а также сложные союзы (ponieważ, dlatego) — ставь A2.
    - Не завышай уровень из вежливости! Будь строг.
    
    Выведи только код уровня (A0, A1, A2, B1).
    """
    
    result = await get_ai_response(prompt, TEST_SYSTEM_PROMPT)
    match = re.search(r'(A[0-2]|B1)', result)
    level = match.group(0) if match else "A1"
    
    await db.update_user_field(message.from_user.id, "language_level", level)
    await message.answer(f"Твой уровень: {level}.\nТеперь напиши /lesson, чтобы начать обучение!")
