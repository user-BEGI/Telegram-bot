import sqlite3
conn = sqlite3.connect('bot_database.db')
cursor = conn.cursor()
try:
    cursor.execute('ALTER TABLE users ADD COLUMN language TEXT DEFAULT "en"')
    conn.commit()
    print("✅ Language column added!")
except:
    print("⚠️ Column already exists.")
conn.close()
