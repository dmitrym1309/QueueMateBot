import sqlite3
import threading
from config import DB_NAME

# Создаем соединение с базой данных
connection = sqlite3.connect(DB_NAME, check_same_thread=False)
cursor = connection.cursor()

# Создаем блокировку для безопасного доступа к базе данных
db_lock = threading.Lock()

def init_database():
    """Инициализация базы данных и создание необходимых таблиц"""
    with db_lock:
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS Chats (
            chat_id INTEGER PRIMARY KEY,
            chat_name TEXT)'''
        )

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS Users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            display_name TEXT
        )
        ''')

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS Queues (
            queue_id INTEGER PRIMARY KEY AUTOINCREMENT,
            queue_name TEXT,
            chat_id INTEGER,
            creator_id INTEGER,
            FOREIGN KEY (chat_id) REFERENCES Chats(chat_id),
            FOREIGN KEY (creator_id) REFERENCES Users(user_id),
            UNIQUE (queue_name, chat_id)  -- Очередь с таким именем может быть только одна в каждой беседе
        )
        ''')

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS QueueMembers (
            queue_id INTEGER,
            user_id INTEGER,
            join_order INTEGER,
            PRIMARY KEY (queue_id, user_id),
            FOREIGN KEY (queue_id) REFERENCES Queues(queue_id),
            FOREIGN KEY (user_id) REFERENCES Users(user_id)
        )
        ''')
        
        connection.commit()

def add_or_update_user(user_id, username, display_name):
    """Добавление или обновление информации о пользователе"""
    with db_lock:
        cursor.execute("INSERT OR REPLACE INTO Users (user_id, username, display_name) VALUES (?, ?, ?)", 
                      (user_id, username, display_name))
        connection.commit()

def get_user_info(user_id):
    """Получение информации о пользователе"""
    with db_lock:
        cursor.execute("SELECT username, display_name FROM Users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        return result if result else (None, None)

def add_chat(chat_id, chat_name):
    """Добавление информации о чате"""
    with db_lock:
        cursor.execute("INSERT OR IGNORE INTO Chats (chat_id, chat_name) VALUES (?, ?)", 
                      (chat_id, chat_name))
        connection.commit()

def create_queue(queue_name, chat_id, creator_id):
    """Создание новой очереди"""
    with db_lock:
        cursor.execute("INSERT INTO Queues (queue_name, chat_id, creator_id) VALUES (?, ?, ?)", 
                      (queue_name, chat_id, creator_id))
        connection.commit()
        return cursor.lastrowid

def get_queue_id(queue_name, chat_id):
    """Получение ID очереди по названию и ID чата"""
    with db_lock:
        cursor.execute("SELECT queue_id FROM Queues WHERE queue_name = ? AND chat_id = ?", 
                      (queue_name, chat_id))
        result = cursor.fetchone()
        return result[0] if result else None

def check_user_in_queue(queue_id, user_id):
    """Проверка, состоит ли пользователь в очереди"""
    with db_lock:
        cursor.execute("SELECT join_order FROM QueueMembers WHERE queue_id = ? AND user_id = ?", 
                      (queue_id, user_id))
        result = cursor.fetchone()
        return result[0] if result else None

def add_user_to_queue(queue_id, user_id):
    """Добавление пользователя в очередь"""
    with db_lock:
        # Определяем порядковый номер для нового участника
        cursor.execute("SELECT MAX(join_order) FROM QueueMembers WHERE queue_id = ?", (queue_id,))
        max_order = cursor.fetchone()[0]
        new_order = 1 if max_order is None else max_order + 1
        
        # Добавляем пользователя в очередь
        cursor.execute("INSERT INTO QueueMembers (queue_id, user_id, join_order) VALUES (?, ?, ?)", 
                      (queue_id, user_id, new_order))
        connection.commit()
        return new_order

def remove_user_from_queue(queue_id, user_id, user_order):
    """Удаление пользователя из очереди"""
    with db_lock:
        # Удаляем пользователя из очереди
        cursor.execute("DELETE FROM QueueMembers WHERE queue_id = ? AND user_id = ?", 
                      (queue_id, user_id))
        
        # Обновляем порядковые номера оставшихся участников
        cursor.execute("""
            UPDATE QueueMembers 
            SET join_order = join_order - 1 
            WHERE queue_id = ? AND join_order > ?
        """, (queue_id, user_order))
        
        connection.commit()

def rejoin_queue(queue_id, user_id):
    """Перемещение пользователя в конец очереди"""
    with db_lock:
        # Проверяем, есть ли пользователь в очереди
        cursor.execute("SELECT join_order FROM QueueMembers WHERE queue_id = ? AND user_id = ?", 
                      (queue_id, user_id))
        result = cursor.fetchone()
        
        if result:
            current_order = result[0]
            
            # Удаляем пользователя из очереди
            cursor.execute("DELETE FROM QueueMembers WHERE queue_id = ? AND user_id = ?", 
                          (queue_id, user_id))
            
            # Обновляем порядковые номера оставшихся участников
            cursor.execute("""
                UPDATE QueueMembers 
                SET join_order = join_order - 1 
                WHERE queue_id = ? AND join_order > ?
            """, (queue_id, current_order))
            
            # Определяем новый порядковый номер для пользователя
            cursor.execute("SELECT MAX(join_order) FROM QueueMembers WHERE queue_id = ?", (queue_id,))
            max_order = cursor.fetchone()[0]
            new_order = 1 if max_order is None else max_order + 1
            
            # Добавляем пользователя в конец очереди
            cursor.execute("INSERT INTO QueueMembers (queue_id, user_id, join_order) VALUES (?, ?, ?)", 
                          (queue_id, user_id, new_order))
            
            connection.commit()
            return new_order
        else:
            # Если пользователя нет в очереди, просто добавляем его
            cursor.execute("SELECT MAX(join_order) FROM QueueMembers WHERE queue_id = ?", (queue_id,))
            max_order = cursor.fetchone()[0]
            new_order = 1 if max_order is None else max_order + 1
            
            cursor.execute("INSERT INTO QueueMembers (queue_id, user_id, join_order) VALUES (?, ?, ?)", 
                          (queue_id, user_id, new_order))
            
            connection.commit()
            return new_order

def get_queue_members(queue_id):
    """Получение списка участников очереди"""
    with db_lock:
        cursor.execute("""
            SELECT u.display_name, u.username, qm.join_order, qm.user_id
            FROM QueueMembers qm 
            JOIN Users u ON qm.user_id = u.user_id 
            WHERE qm.queue_id = ? 
            ORDER BY qm.join_order
        """, (queue_id,))
        return cursor.fetchall()

def get_queue_members_count(queue_id):
    """Получение количества участников в очереди"""
    with db_lock:
        cursor.execute("SELECT COUNT(*) FROM QueueMembers WHERE queue_id = ?", (queue_id,))
        return cursor.fetchone()[0]

def delete_queue(queue_id):
    """Удаление очереди и всех её участников"""
    with db_lock:
        # Удаляем всех участников очереди
        cursor.execute("DELETE FROM QueueMembers WHERE queue_id = ?", (queue_id,))
        
        # Удаляем саму очередь
        cursor.execute("DELETE FROM Queues WHERE queue_id = ?", (queue_id,))
        
        connection.commit()

def get_all_queues(chat_id):
    """Получение списка всех очередей в чате"""
    with db_lock:
        cursor.execute("""
            SELECT q.queue_name, COUNT(qm.user_id) as members_count 
            FROM Queues q 
            LEFT JOIN QueueMembers qm ON q.queue_id = qm.queue_id 
            WHERE q.chat_id = ? 
            GROUP BY q.queue_id, q.queue_name
            ORDER BY q.queue_name
        """, (chat_id,))
        return cursor.fetchall()

def get_queue_creator(queue_id):
    """Получение информации о создателе очереди"""
    with db_lock:
        cursor.execute("""
            SELECT u.display_name 
            FROM Queues q 
            JOIN Users u ON q.creator_id = u.user_id 
            WHERE q.queue_id = ?
        """, (queue_id,))
        result = cursor.fetchone()
        return result[0] if result else None

def update_display_name(user_id, display_name):
    """Обновление отображаемого имени пользователя"""
    with db_lock:
        cursor.execute("UPDATE Users SET display_name = ? WHERE user_id = ?", (display_name, user_id))
        connection.commit()

def update_username(user_id, username):
    """Обновление только username пользователя"""
    with db_lock:
        cursor.execute("UPDATE Users SET username = ? WHERE user_id = ?", (username, user_id))
        connection.commit()

def skip_position_in_queue(queue_id, user_id):
    """Перемещение пользователя на одну позицию назад в очереди"""
    with db_lock:
        # Получаем текущую позицию пользователя
        cursor.execute("SELECT join_order FROM QueueMembers WHERE queue_id = ? AND user_id = ?", 
                      (queue_id, user_id))
        result = cursor.fetchone()
        if not result:
            return False
        
        user_order = result[0]
        
        # Получаем количество участников в очереди
        cursor.execute("SELECT COUNT(*) FROM QueueMembers WHERE queue_id = ?", (queue_id,))
        members_count = cursor.fetchone()[0]
        
        # Проверяем, не последний ли пользователь в очереди
        if user_order == members_count:
            return False
        
        # Обновляем позицию пользователя, который будет перемещен вперед
        cursor.execute("""
            UPDATE QueueMembers 
            SET join_order = ? 
            WHERE queue_id = ? AND join_order = ?
        """, (user_order, queue_id, user_order + 1))
        
        # Обновляем позицию текущего пользователя
        cursor.execute("""
            UPDATE QueueMembers 
            SET join_order = ? 
            WHERE queue_id = ? AND user_id = ?
        """, (user_order + 1, queue_id, user_id))
        
        connection.commit()
        return True

def set_user_position(queue_id, user_id, new_position):
    """Изменение позиции пользователя в очереди"""
    with db_lock:
        # Получаем текущую позицию пользователя
        cursor.execute("SELECT join_order FROM QueueMembers WHERE queue_id = ? AND user_id = ?", 
                      (queue_id, user_id))
        result = cursor.fetchone()
        if not result:
            return False, None
        
        user_order = result[0]
        
        # Если новая позиция совпадает с текущей, ничего не делаем
        if user_order == new_position:
            return False, user_order
        
        # Временно удаляем пользователя из очереди
        cursor.execute("DELETE FROM QueueMembers WHERE queue_id = ? AND user_id = ?", 
                     (queue_id, user_id))
        
        # Если перемещаем вверх (на меньшую позицию)
        if new_position < user_order:
            cursor.execute("""
                UPDATE QueueMembers 
                SET join_order = join_order + 1 
                WHERE queue_id = ? AND join_order >= ? AND join_order < ?
            """, (queue_id, new_position, user_order))
        # Если перемещаем вниз (на большую позицию)
        else:
            cursor.execute("""
                UPDATE QueueMembers 
                SET join_order = join_order - 1 
                WHERE queue_id = ? AND join_order > ? AND join_order <= ?
            """, (queue_id, user_order, new_position))
        
        # Добавляем пользователя на новую позицию
        cursor.execute("INSERT INTO QueueMembers (queue_id, user_id, join_order) VALUES (?, ?, ?)", 
                     (queue_id, user_id, new_position))
        
        connection.commit()
        return True, user_order

def close_connection():
    """Закрытие соединения с базой данных"""
    connection.close() 