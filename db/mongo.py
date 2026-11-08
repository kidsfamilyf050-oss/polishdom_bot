from motor.motor_asyncio import AsyncIOMotorClient
from config import settings
import logging

class Database:
    """
    Класс для работы с базой данных MongoDB.
    Содержит все необходимые методы для работы бота.
    """
    def __init__(self):
        self.client = AsyncIOMotorClient(settings.MONGO_URI)
        self.db = self.client[settings.MONGODB_DB]

    async def get_user(self, user_id: int):
        """Получает профиль одного пользователя по его Telegram ID."""
        return await self.db.users.find_one({"user_id": user_id})

    async def get_all_users(self):
        """Возвращает список всех пользователей (для команды /top)."""
        return await self.db.users.find().to_list(length=None)

    async def create_user(self, user_id: int, username: str):
        """Создает новый профиль пользователя с дефолтными настройками."""
        user_data = {
            "user_id": user_id,
            "username": username,
            "name": None,               # Имя спросим при первом /start
            "language_level": "A0",     # Начинаем с нуля
            "reminder_time": None,      # Время напоминаний
            "learned_words": [],        # Список выученных слов
            "timezone": "Asia/Almaty",  # Часовой пояс по умолчанию
            "perfect_streak": 0,        # Серия уроков без ошибок
            "lessons_completed": 0      # Всего пройдено уроков
        }
        await self.db.users.insert_one(user_data)
        return user_data

    async def update_user_field(self, user_id: int, field: str, value):
        """Обновляет одно конкретное поле в профиле пользователя."""
        await self.db.users.update_one({"user_id": user_id}, {"$set": {field: value}})

    async def add_learned_words(self, user_id: int, words: list):
        """Добавляет новые слова в словарь пользователя (без дубликатов)."""
        if words:
            await self.db.users.update_one(
                {"user_id": user_id}, 
                {"$addToSet": {"learned_words": {"$each": words}}}
            )

    async def increment_field(self, user_id: int, field: str, value: int = 1):
        """Увеличивает числовое значение поля (например, счетчик уроков)."""
        await self.db.users.update_one({"user_id": user_id}, {"$inc": {field: value}})

    async def reset_field(self, user_id: int, field: str, value: int = 0):
        """Сбрасывает значение поля (например, обнуляет серию при ошибке)."""
        await self.db.users.update_one({"user_id": user_id}, {"$set": {field: value}})

    async def get_users_with_reminders(self):
        """Возвращает список пользователей, у которых включены напоминания."""
        cursor = self.db.users.find({"reminder_time": {"$ne": None}})
        return await cursor.to_list(length=None)

db = Database()
