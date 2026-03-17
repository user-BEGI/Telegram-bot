import sqlite3


def migrate():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()

    print("Adding referrer_id column to users table...")
    try:
        # This command adds the new column to your existing table
        cursor.execute('ALTER TABLE users ADD COLUMN referrer_id INTEGER')
        print("✅ Column added successfully!")
    except sqlite3.OperationalError:
        print("⚠️ Column already exists or table doesn't exist.")

    conn.commit()
    conn.close()


if __name__ == "__main__":
    migrate()