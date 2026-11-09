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
    waiting_for_answer = State()

@router.message(Command("test"))
async def start_test(message: Message, state: FSMContext):
    await state.set_state(TestStates.waiting_for_answer)
    await message.answer(
        "📝 <b>Диагностика уровня</b>\n\n"
        "Напиши небольшой текст о себе (5-7 предложений) на польском языке. "
        "Расскажи, как тебя зовут, где живешь, чем занимаешься.\n\n"
        "Если ты совсем не знаешь польский, просто напиши пару предложений на русском.",
        parse_mode="HTML"
    )

@router.message(TestStates.waiting_for_answer)
async def process_test_answer(message: Message, state: FSMContext):
    if not message.text:
        return await message.answer("Пожалуйста, напиши ответ текстом.")

    text = message.text.strip()
    await state.clear()
    await message.answer("🔄 Анализирую твой ответ как строгий экзаменатор...")

    # ЖЕСТКИЙ ПРОМПТ ДЛЯ ЭКЗАМЕНАТОРА
    prompt = f"""
    Ты — строгий экзаменатор по польскому языку (CEFR). 
    Оцени уровень ученика на основе его текста: 
    "{text}"

    ⚠️ ПРАВИЛА ОЦЕНКИ (СОБЛЮДАТЬ СТРОГО):
    - Если текст написан на русском (кириллицей) — ставь только A0.
    - Если ученик использует только простые фразы (меня зовут, я живу) и настоящее время без сложных конструкций — ставь A1.
    - Если есть прошедшее время, винительный/родительный падежи, базовые союзы (i, a, ale) — ставь A2.
    - Если сложные предложения, все падежи, богатый словарный запас — ставь B1 и выше.
    - Не будь вежливым, не завышай оценку! Ошибки в падежах и спряжениях снижают уровень.

    Выведи ТОЛЬКО код уровня (A0, A1, A2, B1, B2, C1, C2) и ничего больше.
    """

    try:
        result = await get_ai_response(prompt, TEST_SYSTEM_PROMPT)
        
        # Ищем уровень в ответе нейросети
        level_match = re.search(r'(A[0-2]|B1|B2|C1|C2)', result)
        
        if level_match:
            level = level_match.group(0)
        else:
            level = "A1" # Если нейросеть запуталась, ставим базовый уровень

        # Обновляем уровень в базе
        await db.update_user_field(message.from_user.id, "language_level", level)

        # Даем обратную связь
        await message.answer(
            f"📊 <b>Результат диагностики:</b>\n\n"
            f"Твой уровень: <b>{level}</b>.\n\n"
            f"Я обновил твой профиль. Теперь уроки будут адаптированы под этот уровень.\n"
            f"Напиши /lesson, чтобы начать!",
            parse_mode="HTML"
        )

    except Exception as e:
        await message.answer("⚠️ Не удалось оценить ответ. Попробуй позже.")
