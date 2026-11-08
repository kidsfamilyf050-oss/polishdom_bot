from motor.motor_asyncio import AsyncIOMotorClient
from config import settings
from datetime import datetime, timedelta

class Database:
    def __init__(self):
        self.client = AsyncIOMotorClient(settings.MONGO_URI)
        self.db = self.client[settings.MONGODB_DB]

    async def ensure_indexes(self):
        await self.db.users.create_index("user_id", unique=True)

    async def get_user(self, user_id):
        return await self.db.users.find_one({"user_id": user_id})

    async def create_user(self, user_id, username):
        data = {
            "user_id": user_id, "username": username, "name": None,
            "language_level": "A0",
            "reminder_time": None,
            "timezone": "Asia/Almaty",
            "learned_words": [],  # [{word, translation, level, learned_at, review_count, next_review_at}]
            "progress": {"streak": 0, "total_lessons": 0, "last_lesson_date": None},
            "created_at": datetime.utcnow(),
        }
        await self.db.users.insert_one(data)
        return data

    async def update_user_field(self, user_id, field, value):
        await self.db.users.update_one({"user_id": user_id}, {"$set": {field: value}})

    async def add_learned_words(self, user_id, words):
        """words: [{word, translation, level}]"""
        now = datetime.utcnow()
        entries = [{
            "word": w["word"], "translation": w.get("translation", ""),
            "level": w.get("level", "A0"),
            "learned_at": now, "review_count": 0,
            "next_review_at": now + timedelta(days=1),
        } for w in words]
        if entries:
            await self.db.users.update_one(
                {"user_id": user_id}, {"$push": {"learned_words": {"$each": entries}}}
            )

    async def get_words_for_review(self, user_id, limit=5):
        user = await self.get_user(user_id)
        if not user:
            return []
        now = datetime.utcnow()
        words = user.get("learned_words", [])
        due = [w for w in words if w.get("next_review_at") and w["next_review_at"] <= now]
        if len(due) < limit:
            cutoff = now - timedelta(days=7)
            recent = [w for w in words if w.get("learned_at") and w["learned_at"] >= cutoff and w not in due]
            due = (due + recent)[:limit]
        return due[:limit]

    async def update_word_after_review(self, user_id, word, correct):
        user = await self.get_user(user_id)
        if not user:
            return
        intervals = [1, 3, 7, 14, 30]
        for w in user.get("learned_words", []):
            if w.get("word") == word:
                rc = w.get("review_count", 0)
                if correct:
                    rc += 1
                    delay = intervals[min(rc, len(intervals) - 1)]
                else:
                    rc, delay = 0, 1
                w["review_count"] = rc
                w["next_review_at"] = datetime.utcnow() + timedelta(days=delay)
        await self.db.users.update_one({"user_id": user_id}, {"$set": {"learned_words": user["learned_words"]}})

    async def update_progress(self, user_id, all_correct):
        user = await self.get_user(user_id)
        if not user:
            return
        prog = user.get("progress") or {"streak": 0, "total_lessons": 0, "last_lesson_date": None}
        prog["total_lessons"] = prog.get("total_lessons", 0) + 1
        prog["last_lesson_date"] = datetime.utcnow()
        prog["streak"] = prog.get("streak", 0) + 1 if all_correct else 0
        await self.db.users.update_one({"user_id": user_id}, {"$set": {"progress": prog}})

    async def get_users_with_reminders(self):
        cursor = self.db.users.find({"reminder_time": {"$ne": None}})
        return await cursor.to_list(length=None)

db = Database()
