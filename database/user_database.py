import aiosqlite

db_name = 'database/user_threads.db'

async def create_table():
    async with aiosqlite.connect(db_name) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS user_threads (
            user_id TEXT PRIMARY KEY,
            thread_id TEXT NOT NULL
        );
        """)
        await db.commit()

async def upsert_user_thread(user_id, thread_id):
    async with aiosqlite.connect(db_name) as db:
        await db.execute("""
            INSERT INTO user_threads (user_id, thread_id)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET 
            thread_id = excluded.thread_id;
        """, (user_id, thread_id))
        await db.commit()

async def get_thread_id(user_id):
    async with aiosqlite.connect(db_name) as db:
        async with db.execute("SELECT thread_id FROM user_threads WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

# Ensure to call these functions in an async context:
# await create_table()
# await upsert_user_thread(your_user_id, your_thread_id)
# your_thread_id = await get_thread_id(your_user_id)