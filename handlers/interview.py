from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from QUESTIONS.INTERVIEW_QUESTIONS import INTERVIEW_QUESTIONS
from ai.openrouter import get_ai_response, INTERVIEW_SYSTEM_PROMPT
from datetime import datetime
import logging
import random
from states.interview import InterviewStates
from utils.markdown import escape_markdown
from utils.audio import transcribe_audio
import os

router = Router()
router.message.filter(F.chat.type == "private")

def get_random_questions(max_count=50):
    all_questions = INTERVIEW_QUESTIONS.copy()
    random.shuffle(all_questions)
    if isinstance(max_count, int) and max_count > 0 and max_count <= len(all_questions):
        return all_questions[:max_count]
    min_questions = 3
    max_questions = min(50 if max_count is None else max_count, len(all_questions))
    question_count = min_questions if min_questions >= max_questions else random.randint(min_questions, max_questions)
    return all_questions[:question_count]

def get_interview_keyboard():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отменить интервью")]], resize_keyboard=True, one_time_keyboard=False)

def get_start_keyboard():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🎯 Начать интервью")]], resize_keyboard=True, one_time_keyboard=True)

@router.message(Command("interview"))
async def cmd_interview(message: Message, state: FSMContext):
    if await state.get_state():
        await message.answer("У вас уже есть активный процесс.", reply_markup=get_interview_keyboard())
        return
    
    message_text = (
        f"🎯 *Тренажер на сдачу экзамена на Карту Поляка*\n\n"
        f"Я буду задавать вопросы, которые могут встретиться на интервью.\n\n"
        f"*Отвечайте на польском языке, и я помогу улучшить ваши ответы.*\n\n"
        f"Также вы можете отвечать голосовыми сообщениями. 🎤"
    )
    await message.answer(escape_markdown(message_text), parse_mode="MarkdownV2", reply_markup=get_start_keyboard())

@router.message(F.text == "🎯 Начать интервью")
@router.message(Command("start_interview"))
async def start_interview(message: Message, state: FSMContext):
    if await state.get_state():
        await message.answer("У вас уже есть активный процесс.", reply_markup=get_interview_keyboard())
        return
    
    random_questions = get_random_questions()
    await state.set_state(InterviewStates.waiting_answer)
    await state.update_data(question_index=0, questions=[], answers=[], interview_questions=random_questions, start_time=datetime.utcnow())
    
    await message.answer(f"Начинаем интервью! Вам будет задано {len(random_questions)} вопросов.", reply_markup=get_interview_keyboard())
    await message.answer(random_questions[0], reply_markup=get_interview_keyboard())

@router.message(F.text == "❌ Отменить интервью")
@router.message(Command("cancel_interview"))
async def cancel_interview(message: Message, state: FSMContext):
    if await state.get_state():
        await state.clear()
        await message.answer("✅ Интервью отменено.", reply_markup=ReplyKeyboardRemove())
    else:
        await message.answer("У вас нет активного интервью.", reply_markup=ReplyKeyboardRemove())

@router.message(StateFilter(InterviewStates.waiting_answer), F.voice)
async def handle_voice_message(message: Message, state: FSMContext):
    file_id = message.voice.file_id
    file = await message.bot.get_file(file_id)
    file_path = f"/tmp/{file_id}.ogg"
    await message.bot.download_file(file.file_path, file_path)
    await message.answer("🔄 Транскрибирую аудио...")
    
    text = await transcribe_audio(file_path)
    os.remove(file_path)
    
    if not text:
        await message.answer("⚠️ Не удалось распознать аудио.")
        return
    await message.answer(f"✅ Распознано: {text}")
    await process_answer(message, state, text)

async def process_answer(message: Message, state: FSMContext, answer_text: str):
    data = await state.get_data()
    question_index = data.get("question_index", 0)
    questions = data.get("questions", [])
    answers = data.get("answers", [])
    interview_questions = data.get("interview_questions", [])
    
    questions.append(interview_questions[question_index])
    answers.append(answer_text)
    next_index = question_index + 1
    
    if next_index < len(interview_questions):
        await state.update_data(question_index=next_index, questions=questions, answers=answers)
        await message.answer(interview_questions[next_index])
    else:
        await message.answer(f"🔄 Интервью завершено! Вы ответили на {len(questions)} вопросов. Анализирую ваши ответы...")
        
        summary_prompt = (
            "Создай краткий отзыв на диалог интервью на Карту Поляка:\n\n"
            "Диалог:\n" +
            "\n".join(f"Консул: {q}\nКандидат: {a}" for q, a in zip(questions, answers)) +
            "\n\n"
            "1. ОТЗЫВ КОНСУЛА (2-3 предложения):\n"
            "Формально сообщи результат: интервью пройдено или не пройдено, без объяснения причин.\n"
            "Например: «Уважаемый кандидат, ваше интервью пройдено. Вы продемонстрировали необходимый уровень знания польской культуры и языка».\n\n"
            "2. ОТЗЫВ УЧИТЕЛЯ:\n"
            "Дружелюбно (с 2-3 эмодзи) отметь 1-2 сильные стороны ответов и 1-2 ключевые области для улучшения с примерами.\n"
            "Пожелай удачи в подготовке."
        )
        
        try:
            summary = await get_ai_response(summary_prompt, INTERVIEW_SYSTEM_PROMPT)
            if not summary: raise ValueError("Пустой ответ от API")
            escaped_summary = escape_markdown(summary)
            await state.clear()
            
            await message.answer(f"🎯 Результат интервью:\n\n{escaped_summary}", parse_mode="MarkdownV2", reply_markup=ReplyKeyboardRemove())
            await message.answer("Хочешь пройти ещё одно интервью? Используй команду /interview", reply_markup=ReplyKeyboardRemove())
            
        except Exception as e:
            logging.error(f"Error analyzing interview results: {e}")
            await message.answer("Произошла ошибка при анализе результатов. Пожалуйста, попробуйте позже.", reply_markup=ReplyKeyboardRemove())
            await state.clear()

@router.message(StateFilter(InterviewStates.waiting_answer), ~F.text.startswith("/"), ~F.text.startswith("❌"))
async def handle_answer(message: Message, state: FSMContext):
    if not message.text or message.text.strip() == "":
        await message.answer("Пожалуйста, введите ответ на вопрос.")
        return
    await process_answer(message, state, message.text)

@router.message(StateFilter(InterviewStates.waiting_answer), F.text.startswith("/"))
async def block_commands(message: Message):
    if message.text not in ["/cancel_interview", "/help"]:
        await message.answer("⚠️ Вы сейчас проходите интервью. Завершите интервью или нажмите '❌ Отменить интервью'.")
