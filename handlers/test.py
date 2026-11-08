import re
from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
import logging
from ai.openrouter import get_ai_response, TEST_SYSTEM_PROMPT
from datetime import datetime
from states.test import TestStates
from utils.markdown import escape_markdown

router = Router()
router.message.filter(F.chat.type == "private")

# Единое открытое задание
OPEN_TASK = "Opowiedz o sobie i o tym, co lubisz robić. Napisz tyle, ile możesz po polsku."
FALLBACK_TASK = "Если ты совсем не знаешь польский, напиши об этом по-русски и расскажи, почему хочешь его выучить."

def get_test_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отменить тест")]],
        resize_keyboard=True,
        one_time_keyboard=False
    )
    return keyboard

def get_start_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📝 Начать тест")]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    return keyboard

@router.message(Command("test"))
async def cmd_test(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state:
        await message.answer("У вас уже есть активный процесс. Завершите его или отмените текущий.", reply_markup=get_test_keyboard())
        return
        
    await message.answer(
        "📝 Тест уровня польского языка\n\n"
        "Я предложу вам один вопрос, который поможет определить ваш уровень владения польским. "
        "На его основе составлю персонализированный план обучения на месяц.",
        reply_markup=get_start_keyboard()
    )

@router.message(F.text == "📝 Начать тест")
@router.message(Command("start_test"))
async def start_test(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state:
        await message.answer("У вас уже есть активный процесс. Завершите его или отмените текущий.", reply_markup=get_test_keyboard())
        return
    
    await state.set_state(TestStates.waiting_answer)
    await state.update_data(start_time=datetime.utcnow())
    
    await message.answer(f"{OPEN_TASK}\n\n{FALLBACK_TASK}", reply_markup=get_test_keyboard())

@router.message(F.text == "❌ Отменить тест")
@router.message(Command("cancel_test"))
async def cancel_test(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state:
        await state.clear()
        await message.answer("✅ Тест отменен.", reply_markup=ReplyKeyboardRemove())
    else:
        await message.answer("У вас нет активного теста.", reply_markup=ReplyKeyboardRemove())

@router.message(StateFilter(TestStates.waiting_answer), ~F.text.startswith("/"), ~F.text.startswith("❌"))
async def handle_answer(message: Message, state: FSMContext):
    if not message.text or message.text.strip() == "":
        await message.answer("Пожалуйста, ответьте на задание.")
        return
    
    user_response = message.text.strip()
    await message.answer("🔄 Анализирую ваш ответ и создаю персонализированный план обучения...")
    
    level = await determine_level(user_response)
    await create_learning_plan(message, state, user_response, level)

async def determine_level(text):
    prompt = (
        "Как опытный преподаватель польского языка, определи уровень владения языком по шкале CEFR (A0, A1, A2, B1, B2, C1, C2) "
        "на основе следующего текста от ученика:\n\n"
        f"{text}\n\n"
        "Если текст написан на русском - это уровень A0. "
        "Анализируй текст по таким критериям: словарный запас, грамматическая сложность, наличие ошибок, "
        "структура предложений, использование времен.\n\n"
        "Верни только код уровня (A0, A1, A2, B1, B2, C1, C2) без пояснений."
    )
    
    try:
        result = await get_ai_response(prompt, TEST_SYSTEM_PROMPT)
        level_match = re.search(r'(A[0-2]|B1|B2|C1|C2)', result)
        if level_match:
            return level_match.group(0)
        return "A1"
    except Exception as e:
        logging.error(f"Error determining level: {e}")
        return "A1"

async def create_learning_plan(message, state, user_response, level):
    summary_prompt = (
        "Ты — опытный преподаватель польского языка. Напиши краткое и мотивирующее сообщение ученику. "
        f"Ученик показал уровень {level}. Вот его ответ:\n\n"
        f"\"{user_response}\"\n\n"
        "Структура сообщения:\n"
        "1. Приветствие.\n"
        f"2. Краткая оценка уровня {level} с одной похвалой.\n"
        "3. Одна главная проблема/зона роста, над которой стоит поработать.\n"
        "4. Краткий план на первую неделю (3-4 пункта: что учить, какие темы).\n"
        "Пиши дружелюбно, тепло, без лишней воды. Не предлагай никаких платных курсов и ссылок."
    )
    
    try:
        plan = await get_ai_response(summary_prompt, TEST_SYSTEM_PROMPT)
        if not plan:
            raise ValueError("Пустой ответ от API")
            
        escaped_plan = escape_markdown(plan)
        
        try:
            from db.mongo import db
            await db.update_user_level(message.from_user.id, level)
            test_data = {
                "user_id": message.from_user.id,
                "username": message.from_user.username,
                "first_name": message.from_user.first_name,
                "last_name": message.from_user.last_name,
                "timestamp": datetime.utcnow(),
                "language_level": level,
                "user_response": user_response,
                "analysis": plan
            }
            
            existing_record = await db.db.test_results.find_one({"user_id": message.from_user.id})
            if existing_record:
                await db.db.test_results.update_one({"user_id": message.from_user.id}, {"$set": test_data})
            else:
                await db.db.test_results.insert_one(test_data)
        except Exception as db_error:
            logging.error(f"Error saving test results to database: {db_error}")
        
        await state.clear()
        await message.answer(
            f"📝 Твой персонализированный план обучения польскому:\n\n{escaped_plan}",
            parse_mode="MarkdownV2",
            reply_markup=ReplyKeyboardRemove()
        )
        await message.answer("Теперь ты можешь использовать команду /word, чтобы учить новые слова с озвучкой!", reply_markup=ReplyKeyboardRemove())
        
    except Exception as e:
        logging.error(f"Error creating learning plan: {e}")
        await message.answer("Произошла ошибка при создании плана обучения. Пожалуйста, попробуйте позже.", reply_markup=ReplyKeyboardRemove())
        await state.clear()

@router.message(StateFilter(TestStates.waiting_answer), F.text.startswith("/"))
async def block_commands(message: Message):
    if message.text not in ["/cancel_test", "/info"]:
        await message.answer("⚠️ Вы сейчас проходите тест. Завершите тест или нажмите '❌ Отменить тест'.")
