import sqlite3


def fix_database():
    # Connect to your database
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()

    print("Checking for missing reward columns...")

    # List of columns to add
    new_columns = [
        ('invited_count', 'INTEGER DEFAULT 0'),
        ('free_passes', 'INTEGER DEFAULT 0')
    ]

    for col_name, col_type in new_columns:
        try:
            # Try to add the column
            cursor.execute(f'ALTER TABLE users ADD COLUMN {col_name} {col_type}')
            print(f"✅ Column '{col_name}' added successfully!")
        except sqlite3.OperationalError:
            # If column already exists, SQLite throws an error, which we ignore
            print(f"⚠️ Column '{col_name}' already exists, skipping.")

    conn.commit()
    conn.close()
    print("✨ Database migration finished!")


if __name__ == "__main__":
    fix_database()