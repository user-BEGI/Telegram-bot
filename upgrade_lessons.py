import sqlite3


def upgrade():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()

    print("Upgrading lessons table...")
    try:
        # 1. Rename video_id to content_id (Modern SQLite supports this)
        cursor.execute('ALTER TABLE lessons RENAME COLUMN video_id TO content_id')
        # 2. Add content_type column (video, photo, document, text)
        cursor.execute('ALTER TABLE lessons ADD COLUMN content_type TEXT DEFAULT "video"')
        print("✅ Database upgraded successfully!")
    except Exception as e:
        print(f"⚠️ Note: {e}")

    conn.commit()
    conn.close()


if __name__ == "__main__":
    upgrade()