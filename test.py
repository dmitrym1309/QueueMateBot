import telebot
import sqlite3
import threading

bot = telebot.TeleBot('7365658286:AAGQ7Ob2FUAH1Vpc0oLSrZebKth7xZ2M3e0')
# Разрешаем использование соединения в разных потоках
connection = sqlite3.connect('botdb.db', check_same_thread=False)
cursor = connection.cursor()

# Создаем блокировку для безопасного доступа к базе данных
db_lock = threading.Lock()

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


# Обработчик команды /start
@bot.message_handler(commands=['start'])
def send_welcome(message):
    welcome_text = """
Привет! Я QueueMateBot - бот для управления очередями в групповых чатах.

Добавьте меня в группу и используйте команду /help, чтобы узнать, как создавать очереди и управлять ими.
"""
    bot.reply_to(message, welcome_text)
    
@bot.message_handler(commands=['help'])
def send_help(message):
    help_text = """
📋 *Список доступных команд:*

*Основные команды:*
/view - показать список всех очередей в чате
/view [название] - показать участников конкретной очереди
/join [название] - присоединиться к очереди
/exit [название] - выйти из очереди
/setname [имя] - установить своё отображаемое имя

*Команды администраторов:*
/create [название] - создать новую очередь
/delete [название] - удалить очередь полностью

*Примеры:*
/create Математика - создать очередь "Математика"
/join Математика - встать в очередь "Математика"
/exit Математика - выйти из очереди "Математика"
/view - посмотреть все очереди
/view Математика - посмотреть очередь "Математика"
/delete Математика - удалить очередь "Математика"
/setname Иван - установить имя "Иван"
"""
    bot.reply_to(message, help_text, parse_mode="Markdown")
    

# Обработчик упоминаний бота в группе
@bot.message_handler(func=lambda message: message.text and '@QueueMateBot' in message.text)
def handle_mention(message):
    bot.reply_to(message, "Вы упомянули меня! Чем могу помочь?")


@bot.message_handler(commands=['create'])
def create_queue(message):
    try:
        # Получаем текст после команды /create
        command_parts = message.text.split(' ', 1)
        
        # Проверяем, указано ли название очереди
        if len(command_parts) < 2:
            bot.reply_to(message, "Пожалуйста, укажите название очереди. Пример: /create Математика")
            return
        
        queue_name = command_parts[1].strip()
        chat_id = message.chat.id
        user_id = message.from_user.id
        
        # Проверяем, является ли пользователь администратором или создателем чата
        chat_member = bot.get_chat_member(chat_id, user_id)
        if chat_member.status not in ['administrator', 'creator']:
            bot.reply_to(message, "Только администраторы могут создавать очереди.")
            return
        
        # Используем блокировку для безопасного доступа к базе данных
        with db_lock:
            # Добавляем чат в таблицу Chats, если его еще нет
            cursor.execute("INSERT OR IGNORE INTO Chats (chat_id, chat_name) VALUES (?, ?)", 
                          (chat_id, message.chat.title))
            
            # Добавляем пользователя в таблицу Users, если его еще нет
            user_name = message.from_user.username or ""
            display_name = message.from_user.first_name
            if message.from_user.last_name:
                display_name += " " + message.from_user.last_name
                
            cursor.execute("INSERT OR IGNORE INTO Users (user_id, username, display_name) VALUES (?, ?, ?)", 
                          (user_id, user_name, display_name))
            
            # Создаем новую очередь
            cursor.execute("INSERT INTO Queues (queue_name, chat_id, creator_id) VALUES (?, ?, ?)", 
                          (queue_name, chat_id, user_id))
            
            # Сохраняем изменения
            connection.commit()
        
        bot.reply_to(message, f"Очередь '{queue_name}' успешно создана! Используйте /join {queue_name} чтобы присоединиться.")
    
    except sqlite3.IntegrityError:
        bot.reply_to(message, f"Очередь с названием '{queue_name}' уже существует в этом чате.")
    except Exception as e:
        bot.reply_to(message, f"Произошла ошибка при создании очереди: {str(e)}")
        with db_lock:
            connection.rollback()

@bot.message_handler(commands=['join'])
def join_queue(message):
    try:
        # Получаем текст после команды /join
        command_parts = message.text.split(' ', 1)
        
        # Проверяем, указано ли название очереди
        if len(command_parts) < 2:
            bot.reply_to(message, "Пожалуйста, укажите название очереди. Пример: /join Математика")
            return
        
        queue_name = command_parts[1].strip()
        chat_id = message.chat.id
        user_id = message.from_user.id
        
        # Используем блокировку для безопасного доступа к базе данных
        with db_lock:
            # Добавляем пользователя в таблицу Users, если его еще нет
            user_name = message.from_user.username or ""
            display_name = message.from_user.first_name
            if message.from_user.last_name:
                display_name += " " + message.from_user.last_name
                
            cursor.execute("INSERT OR IGNORE INTO Users (user_id, username, display_name) VALUES (?, ?, ?)", 
                          (user_id, user_name, display_name))
            
            # Проверяем существование очереди
            cursor.execute("SELECT queue_id FROM Queues WHERE queue_name = ? AND chat_id = ?", 
                          (queue_name, chat_id))
            queue_result = cursor.fetchone()
            
            if not queue_result:
                bot.reply_to(message, f"Очередь '{queue_name}' не найдена в этом чате.")
                return
                
            queue_id = queue_result[0]
            
            # Проверяем, не состоит ли пользователь уже в этой очереди
            cursor.execute("SELECT 1 FROM QueueMembers WHERE queue_id = ? AND user_id = ?", 
                          (queue_id, user_id))
            if cursor.fetchone():
                bot.reply_to(message, f"Вы уже состоите в очереди '{queue_name}'.")
                return
            
            # Определяем порядковый номер для нового участника
            cursor.execute("SELECT MAX(join_order) FROM QueueMembers WHERE queue_id = ?", (queue_id,))
            max_order = cursor.fetchone()[0]
            new_order = 1 if max_order is None else max_order + 1
            
            # Добавляем пользователя в очередь
            cursor.execute("INSERT INTO QueueMembers (queue_id, user_id, join_order) VALUES (?, ?, ?)", 
                          (queue_id, user_id, new_order))
            
            # Сохраняем изменения
            connection.commit()
            
            # Получаем текущий список участников очереди
            cursor.execute("""
                SELECT u.display_name, qm.join_order 
                FROM QueueMembers qm 
                JOIN Users u ON qm.user_id = u.user_id 
                WHERE qm.queue_id = ? 
                ORDER BY qm.join_order
            """, (queue_id,))
            
            queue_members = cursor.fetchall()
            
            # Формируем сообщение со списком участников
            queue_list = "\n".join([f"{i}. {name}" for name, i in queue_members])
            
            bot.reply_to(message, f"Вы успешно присоединились к очереди '{queue_name}'!\n\nТекущая очередь:\n{queue_list}")
    
    except Exception as e:
        bot.reply_to(message, f"Произошла ошибка при присоединении к очереди: {str(e)}")
        with db_lock:
            connection.rollback()

@bot.message_handler(commands=['exit'])
def exit_queue(message):
    try:
        # Получаем текст после команды /exit
        command_parts = message.text.split(' ', 1)
        
        # Проверяем, указано ли название очереди
        if len(command_parts) < 2:
            bot.reply_to(message, "Пожалуйста, укажите название очереди. Пример: /exit Математика")
            return
        
        queue_name = command_parts[1].strip()
        chat_id = message.chat.id
        user_id = message.from_user.id
        
        # Используем блокировку для безопасного доступа к базе данных
        with db_lock:
            # Проверяем существование очереди
            cursor.execute("SELECT queue_id FROM Queues WHERE queue_name = ? AND chat_id = ?", 
                          (queue_name, chat_id))
            queue_result = cursor.fetchone()
            
            if not queue_result:
                bot.reply_to(message, f"Очередь '{queue_name}' не найдена в этом чате.")
                return
                
            queue_id = queue_result[0]
            
            # Проверяем, состоит ли пользователь в этой очереди
            cursor.execute("SELECT join_order FROM QueueMembers WHERE queue_id = ? AND user_id = ?", 
                          (queue_id, user_id))
            member_result = cursor.fetchone()
            
            if not member_result:
                bot.reply_to(message, f"Вы не состоите в очереди '{queue_name}'.")
                return
            
            user_order = member_result[0]
            
            # Удаляем пользователя из очереди
            cursor.execute("DELETE FROM QueueMembers WHERE queue_id = ? AND user_id = ?", 
                          (queue_id, user_id))
            
            # Обновляем порядковые номера оставшихся участников
            cursor.execute("""
                UPDATE QueueMembers 
                SET join_order = join_order - 1 
                WHERE queue_id = ? AND join_order > ?
            """, (queue_id, user_order))
            
            # Сохраняем изменения
            connection.commit()
            
            # Получаем обновленный список участников очереди
            cursor.execute("""
                SELECT u.display_name, qm.join_order 
                FROM QueueMembers qm 
                JOIN Users u ON qm.user_id = u.user_id 
                WHERE qm.queue_id = ? 
                ORDER BY qm.join_order
            """, (queue_id,))
            
            queue_members = cursor.fetchall()
            
            if queue_members:
                # Формируем сообщение со списком участников
                queue_list = "\n".join([f"{i}. {name}" for name, i in queue_members])
                bot.reply_to(message, f"Вы успешно вышли из очереди '{queue_name}'.\n\nОбновленная очередь:\n{queue_list}")
            else:
                bot.reply_to(message, f"Вы успешно вышли из очереди '{queue_name}'.\nОчередь теперь пуста.")
    
    except Exception as e:
        bot.reply_to(message, f"Произошла ошибка при выходе из очереди: {str(e)}")
        with db_lock:
            connection.rollback()

@bot.message_handler(commands=['delete'])
def delete_queue(message):
    try:
        # Получаем текст после команды /delete
        command_parts = message.text.split(' ', 1)
        
        # Проверяем, указано ли название очереди
        if len(command_parts) < 2:
            bot.reply_to(message, "Пожалуйста, укажите название очереди. Пример: /delete Математика")
            return
        
        queue_name = command_parts[1].strip()
        chat_id = message.chat.id
        user_id = message.from_user.id
        
        # Проверяем, является ли пользователь администратором или создателем чата
        chat_member = bot.get_chat_member(chat_id, user_id)
        if chat_member.status not in ['administrator', 'creator']:
            bot.reply_to(message, "Только администраторы могут удалять очереди.")
            return
        
        # Используем блокировку для безопасного доступа к базе данных
        with db_lock:
            # Проверяем существование очереди
            cursor.execute("SELECT queue_id FROM Queues WHERE queue_name = ? AND chat_id = ?", 
                          (queue_name, chat_id))
            queue_result = cursor.fetchone()
            
            if not queue_result:
                bot.reply_to(message, f"Очередь '{queue_name}' не найдена в этом чате.")
                return
                
            queue_id = queue_result[0]
            
            # Получаем количество участников в очереди для информационного сообщения
            cursor.execute("SELECT COUNT(*) FROM QueueMembers WHERE queue_id = ?", (queue_id,))
            members_count = cursor.fetchone()[0]
            
            # Удаляем всех участников очереди
            cursor.execute("DELETE FROM QueueMembers WHERE queue_id = ?", (queue_id,))
            
            # Удаляем саму очередь
            cursor.execute("DELETE FROM Queues WHERE queue_id = ?", (queue_id,))
            
            # Сохраняем изменения
            connection.commit()
            
            bot.reply_to(message, f"Очередь '{queue_name}' успешно удалена. Было удалено {members_count} участников.")
    
    except Exception as e:
        bot.reply_to(message, f"Произошла ошибка при удалении очереди: {str(e)}")
        with db_lock:
            connection.rollback()

@bot.message_handler(commands=['view'])
def view_queue(message):
    try:
        chat_id = message.chat.id
        
        # Получаем текст после команды /view
        command_parts = message.text.split(' ', 1)
        
        # Используем блокировку для безопасного доступа к базе данных
        with db_lock:
            # Если после /view ничего нет, выводим список всех очередей в группе
            if len(command_parts) < 2 or not command_parts[1].strip():
                cursor.execute("""
                    SELECT q.queue_name, COUNT(qm.user_id) as members_count 
                    FROM Queues q 
                    LEFT JOIN QueueMembers qm ON q.queue_id = qm.queue_id 
                    WHERE q.chat_id = ? 
                    GROUP BY q.queue_id, q.queue_name
                    ORDER BY q.queue_name
                """, (chat_id,))
                
                queues = cursor.fetchall()
                
                if not queues:
                    bot.reply_to(message, "В этом чате пока нет очередей. Создайте новую с помощью команды /create.")
                    return
                
                # Формируем сообщение со списком очередей
                queues_list = "\n".join([f"📋 {name} - {count} участник(ов)" for name, count in queues])
                
                bot.reply_to(message, f"Список очередей в этом чате:\n\n{queues_list}\n\nДля просмотра конкретной очереди используйте /view [название очереди]")
            
            # Если указано название очереди, выводим информацию о ней
            else:
                queue_name = command_parts[1].strip()
                
                # Проверяем существование очереди
                cursor.execute("SELECT queue_id FROM Queues WHERE queue_name = ? AND chat_id = ?", 
                              (queue_name, chat_id))
                queue_result = cursor.fetchone()
                
                if not queue_result:
                    bot.reply_to(message, f"Очередь '{queue_name}' не найдена в этом чате.")
                    return
                    
                queue_id = queue_result[0]
                
                # Получаем информацию о создателе очереди
                cursor.execute("""
                    SELECT u.display_name 
                    FROM Queues q 
                    JOIN Users u ON q.creator_id = u.user_id 
                    WHERE q.queue_id = ?
                """, (queue_id,))
                creator_name = cursor.fetchone()[0]
                
                # Получаем список участников очереди
                cursor.execute("""
                    SELECT u.display_name, u.username, qm.join_order 
                    FROM QueueMembers qm 
                    JOIN Users u ON qm.user_id = u.user_id 
                    WHERE qm.queue_id = ? 
                    ORDER BY qm.join_order
                """, (queue_id,))
                
                queue_members = cursor.fetchall()
                
                if not queue_members:
                    bot.reply_to(message, f"Очередь '{queue_name}' пуста. Создатель: {creator_name}")
                    return
                
                # Формируем сообщение со списком участников
                queue_list = "\n".join([
                    f"{i}. {name} (@{username})" if username else f"{i}. {name}"
                    for name, username, i in queue_members
                ])
                
                bot.reply_to(message, f"Очередь '{queue_name}'\nСоздатель: {creator_name}\nКоличество участников: {len(queue_members)}\n\n{queue_list}")
    
    except Exception as e:
        bot.reply_to(message, f"Произошла ошибка при просмотре очереди: {str(e)}")

@bot.message_handler(commands=['setname'])
def set_custom_name(message):
    try:
        # Получаем текст после команды /setname
        command_parts = message.text.split(' ', 1)
        
        # Проверяем, указано ли новое имя
        if len(command_parts) < 2:
            bot.reply_to(message, "Пожалуйста, укажите ваше новое имя. Пример: /setname Иван")
            return
        
        new_name = command_parts[1].strip()
        user_id = message.from_user.id
        
        # Используем блокировку для безопасного доступа к базе данных
        with db_lock:
            cursor.execute("UPDATE Users SET display_name = ? WHERE user_id = ?", 
                          (new_name, user_id))
            connection.commit()
            
        bot.reply_to(message, f"Ваше имя успешно изменено на '{new_name}'!")
    
    except Exception as e:
        bot.reply_to(message, f"Произошла ошибка при изменении имени: {str(e)}")
        with db_lock:
            connection.rollback()

# Запуск бота
bot.polling()