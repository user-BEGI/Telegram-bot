import sqlite3
import time

DB_NAME = 'bot_database.db'

# --- 1. CORE CONNECTION HELPER ---
def get_connection():
    # timeout=20 prevents "Database is locked" errors
    return sqlite3.connect(DB_NAME, timeout=20)


def init_db():
    with get_connection() as conn:
        cursor = conn.cursor()

        # 1. Standard table creation
        cursor.execute('''CREATE TABLE IF NOT EXISTS categories 
                          (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS levels 
                          (id INTEGER PRIMARY KEY AUTOINCREMENT, category_id INTEGER, name TEXT NOT NULL)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS lessons 
                          (id INTEGER PRIMARY KEY AUTOINCREMENT, level_id INTEGER, name TEXT NOT NULL, 
                           content_id TEXT, code TEXT)''')  # video_id renamed to content_id in Step 34
        cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                          (user_id INTEGER PRIMARY KEY, locked_until REAL DEFAULT 0, referrer_id INTEGER,
                           invited_count INTEGER DEFAULT 0, free_passes INTEGER DEFAULT 0)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS channels 
                          (id INTEGER PRIMARY KEY AUTOINCREMENT, channel_id TEXT NOT NULL, url TEXT NOT NULL)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS unlocked_lessons 
                          (user_id INTEGER, lesson_id INTEGER, PRIMARY KEY(user_id, lesson_id))''')

        # 2. SCHEMA MIGRATION (The Fix)
        # This part checks if 'content_type' exists, and adds it if it's missing
        try:
            cursor.execute('ALTER TABLE lessons ADD COLUMN content_type TEXT DEFAULT "video"')
            print("✅ Column 'content_type' added to lessons table.")
        except Exception:
            # If it already exists, SQLite will throw an error, we just ignore it
            pass

        conn.commit()

# --- 2. GETTER FUNCTIONS (Fetch Data) ---

def get_categories():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM categories")
        return cursor.fetchall()

def get_levels(category_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM levels WHERE category_id = ?", (category_id,))
        return cursor.fetchall()

def get_lessons(level_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM lessons WHERE level_id = ?", (level_id,))
        return cursor.fetchall()

def get_lesson_details(lesson_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        # Now we select name, code, content_id, AND content_type
        cursor.execute("SELECT name, code, content_id, content_type FROM lessons WHERE id = ?", (lesson_id,))
        return cursor.fetchone()
def get_user_lockout(user_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT locked_until FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        return result[0] if result else 0

def get_channels():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT channel_id, url FROM channels")
        return cursor.fetchall()

def is_lesson_unlocked(user_id, lesson_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM unlocked_lessons WHERE user_id = ? AND lesson_id = ?", (user_id, lesson_id))
        return cursor.fetchone() is not None

def get_user_unlocked_lessons(user_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT lessons.id, lessons.name 
            FROM lessons 
            JOIN unlocked_lessons ON lessons.id = unlocked_lessons.lesson_id 
            WHERE unlocked_lessons.user_id = ?
        ''', (user_id,))
        return cursor.fetchall()

def get_all_users():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users")
        return [u[0] for u in cursor.fetchall()]

def get_stats():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM lessons")
        total_lessons = cursor.fetchone()[0]
        return total_users, total_lessons

# --- 3. SETTER FUNCTIONS (Add/Update/Delete) ---

def add_category(name):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO categories (name) VALUES (?)", (name,))
        conn.commit()

def add_level(category_id, name):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO levels (category_id, name) VALUES (?, ?)", (category_id, name))
        conn.commit()

def add_lesson(level_id, name, code):
    with get_connection() as conn:
        cursor = conn.cursor()
        # Ensure we are using the 4 columns: level_id, name, code, content_type
        cursor.execute("INSERT INTO lessons (level_id, name, code, content_type) VALUES (?, ?, ?, 'text')",
                       (level_id, name, code))
        last_id = cursor.lastrowid
        conn.commit()
        return last_id

def update_lesson_content(lesson_id, content_id, content_type):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE lessons SET content_id = ?, content_type = ? WHERE id = ?", (content_id, content_type, lesson_id))
        conn.commit()

def set_user_lockout(user_id, duration_seconds):
    with get_connection() as conn:
        cursor = conn.cursor()
        unlock_time = time.time() + duration_seconds
        cursor.execute("INSERT OR REPLACE INTO users (user_id, locked_until) VALUES (?, ?)", (user_id, unlock_time))
        conn.commit()

def save_unlocked_lesson(user_id, lesson_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO unlocked_lessons (user_id, lesson_id) VALUES (?, ?)", (user_id, lesson_id))
        conn.commit()


def add_user(user_id, referrer_id=None):
    with get_connection() as conn:
        cursor = conn.cursor()
        # Check if user is NEW
        cursor.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
        is_new = cursor.fetchone() is None

        # 1. Register the user
        cursor.execute("INSERT OR IGNORE INTO users (user_id, referrer_id) VALUES (?, ?)", (user_id, referrer_id))

        # 2. If it's a NEW user and they were referred, reward the referrer!
        if is_new and referrer_id:
            # Increase referrer's invite count
            cursor.execute("UPDATE users SET invited_count = invited_count + 1 WHERE user_id = ?", (referrer_id,))

            # Check if they reached the goal (5 invites)
            cursor.execute("SELECT invited_count FROM users WHERE user_id = ?", (referrer_id,))
            count = cursor.fetchone()[0]

            if count >= 5:
                # Give a pass and reset the counter
                cursor.execute("UPDATE users SET free_passes = free_passes + 1, invited_count = 0 WHERE user_id = ?",
                               (referrer_id,))
        conn.commit()


def get_user_rewards(user_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT invited_count, free_passes FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()

        # THE FIX: If result is None, return zeros instead of None
        if result:
            return result
        else:
            return (0, 0)

def use_free_pass(user_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET free_passes = free_passes - 1 WHERE user_id = ? AND free_passes > 0",
                       (user_id,))
        conn.commit()

def delete_category(cat_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM categories WHERE id = ?", (cat_id,))
        cursor.execute("DELETE FROM levels WHERE category_id = ?", (cat_id,))
        conn.commit()

def delete_lesson(lsn_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM lessons WHERE id = ?", (lsn_id,))
        cursor.execute("DELETE FROM unlocked_lessons WHERE lesson_id = ?", (lsn_id,))
        conn.commit()

# --- 4. SETUP EXECUTION ---
if __name__ == "__main__":
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM channels")
        channel_list = [
            ('@aboutbegi', 'https://t.me/aboutbegi'),
            ('@learnerorg', 'https://t.me/learnerorg')
        ]
        cursor.executemany("INSERT INTO channels (channel_id, url) VALUES (?, ?)", channel_list)
        conn.commit()
    print("✅ Database initialized and channels added correctly!")
    
def delete_lesson(lsn_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        # 1. Remove the lesson
        cursor.execute("DELETE FROM lessons WHERE id = ?", (lsn_id,))
        # 2. Remove the "Unlocked" status for all users for this lesson
        cursor.execute("DELETE FROM unlocked_lessons WHERE lesson_id = ?", (lsn_id,))
        conn.commit()

def get_all_lessons_extended():
    with get_connection() as conn:
        cursor = conn.cursor()
        # This gets the lesson name PLUS the category and level so you know which is which
        cursor.execute('''
            SELECT lessons.id, lessons.name, levels.name, categories.name 
            FROM lessons 
            JOIN levels ON lessons.level_id = levels.id
            JOIN categories ON levels.category_id = categories.id
        ''')
        return cursor.fetchall()

def delete_multiple_lessons(lsn_ids):
    with get_connection() as conn:
        cursor = conn.cursor()
        # Delete from both tables for every ID in the list
        for lsn_id in lsn_ids:
            cursor.execute("DELETE FROM lessons WHERE id = ?", (lsn_id,))
            cursor.execute("DELETE FROM unlocked_lessons WHERE lesson_id = ?", (lsn_id,))
        conn.commit()

def add_user(user_id, referrer_id=None):
    with get_connection() as conn:
        cursor = conn.cursor()
        # Updated to handle two columns
        cursor.execute("INSERT OR IGNORE INTO users (user_id, referrer_id) VALUES (?, ?)", (user_id, referrer_id))
        conn.commit()

def get_referral_count(user_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users WHERE referrer_id = ?", (user_id,))
        result = cursor.fetchone()
        return result[0] if result else 0

def add_free_passes(user_id, amount):
    with get_connection() as conn:
        cursor = conn.cursor()
        # Increase the free_passes column by the specified amount
        cursor.execute("UPDATE users SET free_passes = free_passes + ? WHERE user_id = ?", (amount, user_id))
        conn.commit()
