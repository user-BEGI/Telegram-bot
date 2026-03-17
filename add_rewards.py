import sqlite3

def upgrade():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    print("Adding reward columns...")
    try:
        cursor.execute('ALTER TABLE users ADD COLUMN invited_count INTEGER DEFAULT 0')
        cursor.execute('ALTER TABLE users ADD COLUMN free_passes INTEGER DEFAULT 0')
        print("✅ Database upgraded with Rewards System!")
    except Exception as e:
        print(f"⚠️ Note: {e}")
    conn.commit()
    conn.close()

if __name__ == "__main__":
    upgrade()