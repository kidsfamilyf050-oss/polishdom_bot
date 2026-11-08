from motor.motor_asyncio import AsyncIOMotorClient
from config import settings


class Database:
    def __init__(self):
        self.client = AsyncIOMotorClient(settings.MONGO_URI)
        self.db = self.client[settings.MONGODB_DB]

    # ------- пользователи -------

    async def get_user(self, user_id: int):
        return await self.db.users.find_one({"user_id": user_id})

    async def create_user(self, user_id: int, username: str):
        user_data = {
            "user_id": user_id,
            "username": username,
            "name": None,
            "language_level": "A0",
            "reminder_time": None,
            "learned_words": [],
            "timezone": "Asia/Almaty",
            "perfect_streak": 0,      # серия идеальных уроков подряд
            "lessons_completed": 0,   # всего пройдено уроков
        }
        await self.db.users.insert_one(user_data)
        return user_data

    async def update_user_field(self, user_id: int, field: str, value):
        await self.db.users.update_one({"user_id": user_id}, {"$set": {field: value}})

    async def increment_field(self, user_id: int, field: str, amount: int = 1):
        """Атомарный $inc — безопасно при параллельных запросах."""
        await self.db.users.update_one({"user_id": user_id}, {"$inc": {field: amount}})

    async def reset_field(self, user_id: int, field: str, value: int = 0):
        await self.db.users.update_one({"user_id": user_id}, {"$set": {field: value}})

    # ------- изученные слова -------

    async def add_learned_word(self, user_id: int, word: str):
        await self.db.users.update_one(
            {"user_id": user_id}, {"$addToSet": {"learned_words": word}}
        )

    async def add_learned_words(self, user_id: int, words):
        """Добавляет список слов (array of str), без дублей."""
        words = [w for w in (words or []) if w]
        if not words:
            return
        await self.db.users.update_one(
            {"user_id": user_id},
            {"$addToSet": {"learned_words": {"$each": words}}},
        )

    # ------- напоминания -------

    async def get_users_with_reminders(self):
        cursor = self.db.users.find({"reminder_time": {"$ne": None}})
        return await cursor.to_list(length=None)


db = Database()
