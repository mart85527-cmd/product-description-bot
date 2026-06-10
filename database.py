import sqlite3
from datetime import datetime

DB_FILE = "bot.db"

def init_db():
    """Создаёт таблицы в базе данных, если их ещё нет."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            balance INTEGER DEFAULT 0,
            created_at TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS generations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            platform TEXT,
            category TEXT,
            tone TEXT,
            result_text TEXT,
            created_at TEXT,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS favorites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            generation_id INTEGER,
            created_at TEXT,
            FOREIGN KEY (user_id) REFERENCES users (user_id),
            FOREIGN KEY (generation_id) REFERENCES generations (id)
        )
    """)

    # Добавляем колонку tone, если таблица уже существовала (для совместимости)
    try:
        cursor.execute("ALTER TABLE generations ADD COLUMN tone TEXT")
    except sqlite3.OperationalError:
        pass  # колонка уже есть

    conn.commit()
    conn.close()

def get_or_create_user(user_id, username, first_name):
    """Возвращает пользователя из базы. Если его нет — создаёт с балансом 0."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()

    if not user:
        now = datetime.now().isoformat()
        cursor.execute(
            "INSERT INTO users (user_id, username, first_name, balance, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, username, first_name, 0, now)
        )
        conn.commit()
        user = (user_id, username, first_name, 0, now)

    conn.close()
    return user

def get_balance(user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else 0

def add_balance(user_id, amount):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

def deduct_balance(user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET balance = balance - 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def save_generation(user_id, platform, category, result_text, tone=None):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    cursor.execute(
        "INSERT INTO generations (user_id, platform, category, tone, result_text, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, platform, category, tone, result_text, now)
    )
    conn.commit()
    generation_id = cursor.lastrowid
    conn.close()
    return generation_id

def get_history(user_id, limit=10):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT platform, category, tone, result_text, created_at FROM generations WHERE user_id = ? ORDER BY id DESC LIMIT ?",
        (user_id, limit)
    )
    rows = cursor.fetchall()
    conn.close()
    return rows

def add_favorite(user_id, generation_id):
    """Добавляет генерацию в избранное."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    cursor.execute(
        "INSERT INTO favorites (user_id, generation_id, created_at) VALUES (?, ?, ?)",
        (user_id, generation_id, now)
    )
    conn.commit()
    conn.close()

def get_favorites(user_id, limit=10):
    """Возвращает избранные генерации пользователя."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT g.platform, g.category, g.tone, g.result_text, g.created_at, f.id
        FROM favorites f
        JOIN generations g ON f.generation_id = g.id
        WHERE f.user_id = ?
        ORDER BY f.id DESC
        LIMIT ?
    """, (user_id, limit))
    rows = cursor.fetchall()
    conn.close()
    return rows

def remove_favorite(favorite_id):
    """Удаляет запись из избранного."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM favorites WHERE id = ?", (favorite_id,))
    conn.commit()
    conn.close()
