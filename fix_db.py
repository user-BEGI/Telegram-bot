import sqlite3

def fix():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    # Force create the users table
    print("Creating users table...")
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            locked_until REAL DEFAULT 0
        )
    ''')
    
    conn.commit()
    conn.close()
    print("Database fixed successfully!")

if __name__ == "__main__":
    fix()
