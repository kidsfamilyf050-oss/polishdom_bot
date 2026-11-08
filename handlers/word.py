import os
import uuid
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, FSInputFile
from ai.openrouter import get_ai_response, WORD_SYSTEM_PROMPT
from db.mongo import db
import edge_tts

router = Router()

@router.message(Command("word"))
async def cmd_word(message: Message):
    user = await db.get_user(message.from_user.id)
    level = user.get("language_level", "A1") if user else "A1"
    
    await message.answer("🔄 Подбираю новое слово и готовлю озвучку...")
    
    prompt = f"Сгенерируй одно случайное польское слово и пример для уровня {level}. Строго в формате: слово|перевод|пример на польском|перевод примера."
    
    try:
        response = await get_ai_response(prompt, WORD_SYSTEM_PROMPT)
        parts = response.split("|")
        
        if len(parts) >= 4:
            word, translation, example_pl, example_ru = [p.strip() for p in parts[:4]]
            text_to_speak = f"{word}. {example_pl}"
            
            filename = f"audio_{uuid.uuid4().hex}.mp3"
            voice = os.getenv("EDGE_TTS_VOICE", "pl-PL-MarekNeural")
            communicate = edge_tts.Communicate(text_to_speak, voice)
            await communicate.save(filename)
            
            await message.answer(
                f"🇵🇱 **{word}** — {translation}\n\n"
                f"📖 *Пример:* {example_pl}\n"
                f"🇷🇺 *Перевод:* {example_ru}",
                parse_mode="Markdown"
            )
            
            audio_file = FSInputFile(filename)
            await message.answer_voice(audio_file, caption="🔊 Послушай правильное произношение")
            
            os.remove(filename)
        else:
            await message.answer("⚠️ Не удалось сгенерировать слово. Попробуй еще раз.")
    except Exception as e:
        print(f"Error in word handler: {e}")
        await message.answer("⚠️ Произошла ошибка при создании слова.")
