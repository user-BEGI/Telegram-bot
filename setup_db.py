import sqlite3

def master_setup():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()

    print("Cleaning up old data...")
    cursor.execute("DROP TABLE IF EXISTS channels")
    cursor.execute("DROP TABLE IF EXISTS users")
    cursor.execute("DROP TABLE IF EXISTS categories")
    cursor.execute("DROP TABLE IF EXISTS levels")
    cursor.execute("DROP TABLE IF EXISTS lessons")

    # Create all tables
    cursor.execute('CREATE TABLE categories (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL)')
    cursor.execute('CREATE TABLE levels (id INTEGER PRIMARY KEY AUTOINCREMENT, category_id INTEGER, name TEXT NOT NULL)')
    cursor.execute('CREATE TABLE lessons (id INTEGER PRIMARY KEY AUTOINCREMENT, level_id INTEGER, name TEXT NOT NULL, video_id TEXT, code TEXT)')
    cursor.execute('CREATE TABLE users (user_id INTEGER PRIMARY KEY, locked_until REAL DEFAULT 0)')
    cursor.execute('CREATE TABLE channels (id INTEGER PRIMARY KEY AUTOINCREMENT, channel_id TEXT NOT NULL, url TEXT NOT NULL)')

    # --- ADD YOUR REAL DATA ---
    print("Adding your channels...")
    
    # 1. Add your real channels here
    channel_list = [
        ('@aboutbegi', 'https://t.me/aboutbegi'),
        ('@learnerorg', 'https://t.me/learnerorg')
    ]
    cursor.executemany("INSERT INTO channels (channel_id, url) VALUES (?, ?)", channel_list)

    # 2. Add test lesson again so the bot isn't empty
    cursor.execute("INSERT INTO categories (name) VALUES ('English')")
    cat_id = cursor.lastrowid
    cursor.execute("INSERT INTO levels (category_id, name) VALUES (?, 'Beginner')", (cat_id,))
    lvl_id = cursor.lastrowid
    cursor.execute("INSERT INTO lessons (level_id, name, code) VALUES (?, 'Lesson 1', '1234')", (lvl_id,))

    conn.commit()
    conn.close()
    print("✅ setup_db.py: Database updated with YOUR channels!")

if __name__ == "__main__":
    master_setup()