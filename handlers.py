import telebot
import sqlite3
from config import BOT_TOKEN, MESSAGES
import database as db

# Создаем экземпляр бота
bot = telebot.TeleBot(BOT_TOKEN)

# Обработчик команды /start
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, MESSAGES['welcome'], parse_mode="Markdown")
    
# Обработчик команды /help
@bot.message_handler(commands=['help'])
def send_help(message):
    bot.reply_to(message, MESSAGES['help'], parse_mode="Markdown")
    
# Обработчик упоминаний бота в группе
@bot.message_handler(func=lambda message: message.text and '@QueueMateBot' in message.text)
def handle_mention(message):
    bot.reply_to(message, "Вы упомянули меня! Чем могу помочь?")

# Обработчик команды /create
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
        
        # Добавляем чат в базу данных
        db.add_chat(chat_id, message.chat.title)
        
        # Добавляем пользователя в базу данных
        user_name = message.from_user.username or ""
        update_user_info(user_id, user_name, message.from_user.first_name, message.from_user.last_name)
        
        # Создаем новую очередь
        db.create_queue(queue_name, chat_id, user_id)
        
        bot.reply_to(message, f"Очередь '*{queue_name}*' успешно создана! Используйте `/join {queue_name}` чтобы присоединиться.", parse_mode="Markdown")
    
    except sqlite3.IntegrityError:
        bot.reply_to(message, f"Очередь с названием '{queue_name}' уже существует в этом чате.")
    except Exception as e:
        bot.reply_to(message, f"Произошла ошибка при создании очереди: {str(e)}")

# Обработчик команды /join
@bot.message_handler(commands=['join'])
def join_queue(message):
    try:
        # Получаем текст после команды /join
        command_parts = message.text.split(' ', 1)
        
        # Проверяем, указано ли название очереди
        if len(command_parts) < 2:
            bot.reply_to(message, "Пожалуйста, укажите название очереди. Пример: `/join Математика`", parse_mode="Markdown")
            return
        
        queue_name = command_parts[1].strip()
        chat_id = message.chat.id
        user_id = message.from_user.id
        
        # Добавляем пользователя в базу данных
        user_name = message.from_user.username or ""
        update_user_info(user_id, user_name, message.from_user.first_name, message.from_user.last_name)
        
        # Проверяем существование очереди
        queue_id = db.get_queue_id(queue_name, chat_id)
        if not queue_id:
            bot.reply_to(message, f"Очередь '{queue_name}' не найдена в этом чате.")
            return
        
        # Проверяем, не состоит ли пользователь уже в этой очереди
        if db.check_user_in_queue(queue_id, user_id):
            bot.reply_to(message, f"Вы уже состоите в очереди '{queue_name}'.")
            return
        
        # Добавляем пользователя в очередь
        db.add_user_to_queue(queue_id, user_id)
        
        # Формируем сообщение с информацией об очереди
        queue_info = format_queue_info(queue_name, queue_id)
        
        bot.reply_to(message, f"Вы успешно присоединились к очереди '*{queue_name}*'!\n\n{queue_info}", parse_mode="Markdown")
    
    except Exception as e:
        bot.reply_to(message, f"Произошла ошибка при присоединении к очереди: {str(e)}")

# Обработчик команды /exit
@bot.message_handler(commands=['exit'])
def exit_queue(message):
    try:
        # Получаем текст после команды /exit
        command_parts = message.text.split(' ', 1)
        
        # Проверяем, указано ли название очереди
        if len(command_parts) < 2:
            bot.reply_to(message, "Пожалуйста, укажите название очереди. Пример: `/exit Математика`", parse_mode="Markdown")
            return
        
        queue_name = command_parts[1].strip()
        chat_id = message.chat.id
        user_id = message.from_user.id
        
        # Проверяем существование очереди
        queue_id = db.get_queue_id(queue_name, chat_id)
        if not queue_id:
            bot.reply_to(message, f"Очередь '{queue_name}' не найдена в этом чате.")
            return
        
        # Проверяем, состоит ли пользователь в этой очереди
        user_order = db.check_user_in_queue(queue_id, user_id)
        if not user_order:
            bot.reply_to(message, f"Вы не состоите в очереди '{queue_name}'.")
            return
        
        # Удаляем пользователя из очереди
        db.remove_user_from_queue(queue_id, user_id, user_order)
        
        # Получаем обновленный список участников очереди
        queue_members = db.get_queue_members(queue_id)
        
        if queue_members:
            # Формируем сообщение с информацией об очереди
            queue_info = format_queue_info(queue_name, queue_id)
            
            bot.reply_to(message, f"Вы успешно вышли из очереди '*{queue_name}*'.\n\n{queue_info}", parse_mode="Markdown")
        else:
            bot.reply_to(message, f"Вы успешно вышли из очереди '{queue_name}'.\nОчередь теперь пуста.")
    
    except Exception as e:
        bot.reply_to(message, f"Произошла ошибка при выходе из очереди: {str(e)}")

# Обработчик команды /rejoin
@bot.message_handler(commands=['rejoin'])
def rejoin_queue(message):
    try:
        # Получаем текст после команды /rejoin
        command_parts = message.text.split(' ', 1)
        
        # Проверяем, указано ли название очереди
        if len(command_parts) < 2:
            bot.reply_to(message, "Пожалуйста, укажите название очереди. Пример: `/rejoin Математика`", parse_mode="Markdown")
            return
        
        queue_name = command_parts[1].strip()
        chat_id = message.chat.id
        user_id = message.from_user.id
        
        # Проверяем существование очереди
        queue_id = db.get_queue_id(queue_name, chat_id)
        if not queue_id:
            bot.reply_to(message, f"Очередь '{queue_name}' не найдена в этом чате.")
            return
        
        # Проверяем, состоит ли пользователь в этой очереди
        user_order = db.check_user_in_queue(queue_id, user_id)
        if not user_order:
            bot.reply_to(message, f"Вы не состоите в очереди '*{queue_name}*'. Используйте `/join {queue_name}` чтобы присоединиться.", parse_mode="Markdown")
            return
        
        # Используем функцию rejoin_queue из базы данных вместо ручного удаления и добавления
        db.rejoin_queue(queue_id, user_id)
        
        # Формируем сообщение с информацией об очереди
        queue_info = format_queue_info(queue_name, queue_id)
        
        bot.reply_to(message, f"Вы успешно переместились в конец очереди '*{queue_name}*'.\n\n{queue_info}", parse_mode="Markdown")
    
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"Ошибка в rejoin_queue: {error_details}")
        bot.reply_to(message, f"Произошла ошибка при перемещении в конец очереди: {str(e)}")

# Обработчик команды /delete
@bot.message_handler(commands=['delete'])
def delete_queue(message):
    try:
        # Получаем текст после команды /delete
        command_parts = message.text.split(' ', 1)
        
        # Проверяем, указано ли название очереди
        if len(command_parts) < 2:
            bot.reply_to(message, "Пожалуйста, укажите название очереди. Пример: `/delete Математика`", parse_mode="Markdown")
            return
        
        queue_name = command_parts[1].strip()
        chat_id = message.chat.id
        user_id = message.from_user.id
        
        # Проверяем, является ли пользователь администратором или создателем чата
        chat_member = bot.get_chat_member(chat_id, user_id)
        if chat_member.status not in ['administrator', 'creator']:
            bot.reply_to(message, "Только администраторы могут удалять очереди.")
            return
        
        # Проверяем существование очереди
        queue_id = db.get_queue_id(queue_name, chat_id)
        if not queue_id:
            bot.reply_to(message, f"Очередь '{queue_name}' не найдена в этом чате.")
            return
        
        # Получаем количество участников в очереди для информационного сообщения
        members_count = db.get_queue_members_count(queue_id)
        
        # Удаляем очередь
        db.delete_queue(queue_id)
        
        bot.reply_to(message, f"Очередь '{queue_name}' успешно удалена. Было удалено {members_count} участников.")
    
    except Exception as e:
        bot.reply_to(message, f"Произошла ошибка при удалении очереди: {str(e)}")

# Обработчик команды /view
@bot.message_handler(commands=['view'])
def view_queue(message):
    try:
        chat_id = message.chat.id
        
        # Получаем текст после команды /view
        command_parts = message.text.split(' ', 1)
        
        # Если после /view ничего нет, выводим список всех очередей в группе
        if len(command_parts) < 2 or not command_parts[1].strip():
            queues = db.get_all_queues(chat_id)
            
            if not queues:
                bot.reply_to(message, "В этом чате пока нет очередей. Создайте новую с помощью команды `/create`.", parse_mode="Markdown")
                return
            
            # Формируем сообщение со списком очередей
            queues_list = "\n".join([f"📋 {name} - {count} участник(ов)" for name, count in queues])
            
            bot.reply_to(message, f"Список очередей в этом чате:\n\n{queues_list}\n\nДля просмотра конкретной очереди используйте `/view [название очереди]`", parse_mode="Markdown")
        
        # Если указано название очереди, выводим информацию о ней
        else:
            queue_name = command_parts[1].strip()
            
            # Проверяем существование очереди
            queue_id = db.get_queue_id(queue_name, chat_id)
            if not queue_id:
                bot.reply_to(message, f"Очередь '{queue_name}' не найдена в этом чате.")
                return
            
            # Формируем сообщение с информацией об очереди
            queue_info = format_queue_info(queue_name, queue_id)
            
            bot.reply_to(message, queue_info, parse_mode="Markdown")
    
    except Exception as e:
        bot.reply_to(message, f"Произошла ошибка при просмотре очереди: {str(e)}")

# Обработчик команды /setname
@bot.message_handler(commands=['setname'])
def set_custom_name(message):
    try:
        # Получаем текст после команды /setname
        command_parts = message.text.split(' ', 1)
        
        # Проверяем, указано ли новое имя
        if len(command_parts) < 2:
            bot.reply_to(message, "Пожалуйста, укажите ваше новое имя. Пример: `/setname Иван`", parse_mode="Markdown")
            return
        
        new_name = command_parts[1].strip()
        user_id = message.from_user.id
        
        # Обновляем имя пользователя в базе данных
        db.update_user_display_name(user_id, new_name)
        
        # Получаем список всех чатов, в которых пользователь состоит в очередях
        chat_id = message.chat.id
        
        # Получаем список всех очередей в текущем чате
        queues = db.get_all_queues(chat_id)
        
        # Проверяем, в каких очередях состоит пользователь
        user_queues = []
        for queue_name, _ in queues:
            queue_id = db.get_queue_id(queue_name, chat_id)
            if db.check_user_in_queue(queue_id, user_id):
                user_queues.append(queue_name)
        
        if user_queues:
            queue_list = ", ".join([f"'{name}'" for name in user_queues])
            bot.reply_to(message, f"Ваше имя успешно изменено на '{new_name}'! Новое имя будет отображаться в очередях: {queue_list}")
        else:
            bot.reply_to(message, f"Ваше имя успешно изменено на '{new_name}'! Вы не состоите ни в одной очереди в этом чате.")
    
    except Exception as e:
        bot.reply_to(message, f"Произошла ошибка при изменении имени: {str(e)}")

# Вспомогательная функция для форматирования вывода очереди
def format_queue_info(queue_name, queue_id):
    # Получаем информацию о создателе очереди
    creator_name = db.get_queue_creator(queue_id)
    
    # Получаем список участников очереди
    queue_members = db.get_queue_members(queue_id)
    
    if not queue_members:
        return f"Очередь '*{queue_name}*' пуста.\nСоздатель: _{creator_name}_"
    
    # Формируем сообщение со списком участников без моноширинного шрифта для чисел
    queue_list = "\n".join([
        f"{order}. {name} (@{username})" if username else f"{order}. {name}"
        for name, username, order, _ in queue_members
    ])
    
    return f"Очередь '*{queue_name}*'\nСоздатель: _{creator_name}_\nКоличество участников: {len(queue_members)}\n\n{queue_list}"

# Вспомогательная функция для обновления информации о пользователе
def update_user_info(user_id, username, first_name, last_name):
    # Проверяем, есть ли у пользователя уже установленное имя
    cursor = db.connection.cursor()
    cursor.execute("SELECT display_name FROM Users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    
    # Если пользователь уже существует в базе, не обновляем его имя
    if result:
        # Обновляем только username, если он изменился
        db.cursor.execute("UPDATE Users SET username = ? WHERE user_id = ?", (username, user_id))
        db.connection.commit()
    else:
        # Если пользователя нет в базе, добавляем его с именем из Telegram
        display_name = first_name
        if last_name:
            display_name += " " + last_name
        db.add_or_update_user(user_id, username, display_name)

# Функция для запуска бота
def start_bot():
    bot.polling() 