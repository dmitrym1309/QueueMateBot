import telebot
import sqlite3
import threading
import time
import os
import functools
import collections
from config import BOT_TOKEN, MESSAGES
import database as db
import logging
from telebot import types  # Добавляем импорт для работы с кнопками

# Настройка логирования
logger = logging.getLogger(__name__)

# Создаем экземпляр бота
bot = telebot.TeleBot(BOT_TOKEN)

# Глобальная переменная для контроля работы бота
bot_running = True

# Системы защиты от спама и флуда

# Словари для отслеживания использования команд
command_usage = {}  # Для индивидуальных пользователей
chat_command_usage = {}  # Для групповых чатов
join_queue_usage = {}  # Специально для команды присоединения к очереди

# Настройки ограничений
RATE_LIMITS = {
    'default': {'count': 5, 'period': 60},  # 5 команд в минуту для обычных команд
    'join': {'count': 30, 'period': 60},    # 30 присоединений к очереди в минуту
    'chat': {'count': 30, 'period': 60}     # 30 команд в минуту для всего чата
}

def check_rate_limit(user_id, command_type='default', chat_id=None):
    """
    Проверяет, не превышен ли лимит использования команд.
    
    Args:
        user_id: ID пользователя
        command_type: Тип команды ('default', 'join', 'chat')
        chat_id: ID чата (для групповых ограничений)
        
    Returns:
        tuple: (is_limited, wait_time) - превышен ли лимит и время ожидания
    """
    current_time = time.time()
    
    # Выбираем соответствующий словарь и настройки в зависимости от типа команды
    if command_type == 'join':
        usage_dict = join_queue_usage
        limit_settings = RATE_LIMITS['join']
    elif command_type == 'chat' and chat_id:
        usage_dict = chat_command_usage
        limit_settings = RATE_LIMITS['chat']
        key = str(chat_id)
    else:
        usage_dict = command_usage
        limit_settings = RATE_LIMITS['default']
        key = str(user_id)
    
    # Для индивидуальных ограничений используем ID пользователя
    if command_type != 'chat':
        key = str(user_id)
    
    # Инициализируем очередь временных меток, если её еще нет
    if key not in usage_dict:
        usage_dict[key] = collections.deque()
    
    # Удаляем устаревшие временные метки
    while usage_dict[key] and current_time - usage_dict[key][0] > limit_settings['period']:
        usage_dict[key].popleft()
    
    # Проверяем, не превышен ли лимит
    if len(usage_dict[key]) >= limit_settings['count']:
        # Вычисляем, сколько нужно подождать до освобождения слота
        wait_time = int(usage_dict[key][0] + limit_settings['period'] - current_time) + 1
        return True, wait_time
    
    # Добавляем текущую временную метку
    usage_dict[key].append(current_time)
    return False, 0

def rate_limit_decorator(command_type='default'):
    """
    Декоратор для ограничения частоты использования команд.
    
    Args:
        command_type: Тип команды ('default', 'join', 'chat')
        
    Returns:
        Декоратор функции
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(message, *args, **kwargs):
            user_id = message.from_user.id
            chat_id = message.chat.id
            
            # Проверяем индивидуальное ограничение
            is_limited, wait_time = check_rate_limit(user_id, command_type)
            
            if is_limited:
                logger.warning(f"Rate limit exceeded for user {user_id}, command type {command_type}")
                try:
                    safe_reply_to(message, f"Пожалуйста, не отправляйте команды слишком часто. Попробуйте снова через {wait_time} сек.")
                except Exception as e:
                    logger.error(f"Failed to send rate limit message: {str(e)}")
                return
            
            # Для групповых чатов проверяем также общее ограничение чата
            if message.chat.type in ['group', 'supergroup']:
                is_chat_limited, chat_wait_time = check_rate_limit(None, 'chat', chat_id)
                
                if is_chat_limited:
                    logger.warning(f"Chat rate limit exceeded for chat {chat_id}")
                    # Для чата не отправляем сообщение, чтобы не спамить
                    return
            
            # Если лимиты не превышены, выполняем функцию
            return func(message, *args, **kwargs)
        return wrapper
    return decorator

# Декоратор для повторных попыток при ошибке превышения лимита запросов
def retry_on_rate_limit(max_retries=3, initial_delay=1):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            retries = 0
            delay = initial_delay
            
            while retries <= max_retries:
                try:
                    return func(*args, **kwargs)
                except telebot.apihelper.ApiTelegramException as e:
                    if "Too Many Requests" in str(e) or e.error_code == 429:
                        retry_after = delay
                        
                        # Пытаемся получить время ожидания из ответа
                        if hasattr(e, 'result') and isinstance(e.result, dict):
                            if 'parameters' in e.result and 'retry_after' in e.result['parameters']:
                                retry_after = e.result['parameters']['retry_after']
                        
                        if retries < max_retries:
                            logger.warning(f"Rate limit exceeded. Retry {retries+1}/{max_retries} after {retry_after} seconds")
                            time.sleep(retry_after)
                            retries += 1
                            delay *= 2  # Экспоненциальное увеличение задержки
                        else:
                            logger.error(f"Max retries exceeded for rate limit. Giving up.")
                            raise
                    else:
                        # Другие ошибки API пробрасываем дальше
                        raise
        return wrapper
    return decorator

# Безопасные функции для работы с API Telegram
@retry_on_rate_limit()
def safe_send_message(chat_id, text, **kwargs):
    return bot.send_message(chat_id, text, **kwargs)

@retry_on_rate_limit()
def safe_edit_message_text(chat_id, message_id, text, **kwargs):
    return bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, **kwargs)

@retry_on_rate_limit()
def safe_answer_callback_query(callback_query_id, text, **kwargs):
    return bot.answer_callback_query(callback_query_id, text, **kwargs)

@retry_on_rate_limit()
def safe_reply_to(message, text, **kwargs):
    return bot.reply_to(message, text, **kwargs)

# Функция для обработки ошибок
def handle_error(message, error, operation):
    error_text = str(error)
    logger.error(f"Error during {operation}: {error_text}", exc_info=True)
    try:
        safe_reply_to(message, f"Произошла ошибка при {operation}: {error_text}")
    except Exception as e:
        logger.error(f"Failed to send error message: {str(e)}")

# Обработчик команды /start
@bot.message_handler(commands=['start'])
@rate_limit_decorator('default')
def send_welcome(message):
    try:
        # Добавляем пользователя в базу данных
        user_id = message.from_user.id
        username = message.from_user.username or ""
        update_user_info(user_id, username, message.from_user.first_name, message.from_user.last_name)
        
        # Отправляем приветственное сообщение
        safe_reply_to(message, MESSAGES['welcome'], parse_mode="Markdown")
    except Exception as e:
        handle_error(message, e, "отправке приветствия")
    
# Обработчик команды /help
@bot.message_handler(commands=['help'])
@rate_limit_decorator('default')
def send_help(message):
    try:
        safe_reply_to(message, MESSAGES['help'], parse_mode="Markdown")
    except Exception as e:
        handle_error(message, e, "отправке справки")
    
# Обработчик упоминаний бота в группе
@bot.message_handler(func=lambda message: message.text and '@QueueMateBot' in message.text)
@rate_limit_decorator('default')
def handle_mention(message):
    # Получаем список очередей в текущем чате
    chat_id = message.chat.id
    queues = db.get_all_queues(chat_id)
    
    # Формируем сообщение с информацией о боте и доступных командах
    response = "👋 *Привет! Я QueueMateBot - бот для управления очередями.*\n\n"
    
    # Добавляем информацию о существующих очередях
    if queues:
        response += "*Активные очереди в этом чате:*\n"
        for name, count in queues:
            response += f"📋 {name} - {count} участник(ов)\n"
        response += "\n"
    else:
        response += "*В этом чате пока нет очередей.*\n\n"
    
    # Добавляем краткую справку по основным командам
    response += "*Основные команды:*\n"
    response += "`/view` - список всех очередей\n"
    response += "`/join [название]` - присоединиться к очереди\n"
    response += "`/exit [название]` - выйти из очереди\n"
    response += "`/help` - полный список команд\n"
    
    bot.reply_to(message, response, parse_mode="Markdown")

# Обработчик команды /create
@bot.message_handler(commands=['create'])
@rate_limit_decorator('default')
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
        handle_error(message, e, "создании очереди")

# Вспомогательная функция для форматирования вывода очереди
def format_queue_info(queue_name, queue_id):
    # Получаем информацию о создателе очереди
    creator_name = db.get_queue_creator(queue_id)
    
    # Получаем список участников очереди
    queue_members = db.get_queue_members(queue_id)
    
    if not queue_members:
        return f"Очередь '*{queue_name}*' пуста.\nСоздатель: _{creator_name}_"
    
    # Ограничиваем количество участников для отображения
    max_members_to_show = 50
    total_members = len(queue_members)
    
    if total_members > max_members_to_show:
        queue_members = queue_members[:max_members_to_show]
    
    # Экранируем специальные символы в именах пользователей
    queue_list = []
    for name, username, order, _ in queue_members:
        # Экранируем специальные символы в имени
        safe_name = name.replace('*', '\\*').replace('_', '\\_').replace('`', '\\`').replace('[', '\\[')
        
        if username:
            # Экранируем специальные символы в username
            safe_username = username.replace('*', '\\*').replace('_', '\\_').replace('`', '\\`').replace('[', '\\[')
            queue_list.append(f"{order}. {safe_name} (@{safe_username})")
        else:
            queue_list.append(f"{order}. {safe_name}")
    
    # Соединяем список в строку
    queue_list_text = "\n".join(queue_list)
    
    # Экранируем специальные символы в имени создателя
    safe_creator_name = creator_name.replace('*', '\\*').replace('_', '\\_').replace('`', '\\`').replace('[', '\\[')
    
    result = f"Очередь '*{queue_name}*'\nСоздатель: _{safe_creator_name}_\nКоличество участников: {total_members}"
    
    if total_members > max_members_to_show:
        result += f"\n\nПоказаны первые {max_members_to_show} из {total_members} участников:\n\n{queue_list_text}"
    else:
        result += f"\n\n{queue_list_text}"
    
    return result

# Функция для создания клавиатуры с кнопками для управления очередью
def create_queue_keyboard(queue_name):
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    join_button = types.InlineKeyboardButton("Присоединиться", callback_data=f"join_{queue_name}")
    exit_button = types.InlineKeyboardButton("Выйти", callback_data=f"exit_{queue_name}")
    rejoin_button = types.InlineKeyboardButton("В конец", callback_data=f"rejoin_{queue_name}")
    
    # Размещаем кнопку "Присоединиться" в первом ряду
    keyboard.row(join_button)
    # Размещаем кнопки "Выйти" и "В конец" во втором ряду
    keyboard.row(exit_button, rejoin_button)
    
    return keyboard

# Обработчик команды /join
@bot.message_handler(commands=['join'])
@rate_limit_decorator('join')
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
        
        # Создаем клавиатуру с кнопками
        keyboard = create_queue_keyboard(queue_name)
        
        bot.reply_to(message, f"Вы успешно присоединились к очереди '*{queue_name}*'!\n\n{queue_info}", parse_mode="Markdown", reply_markup=keyboard)
    
    except Exception as e:
        handle_error(message, e, "присоединении к очереди")

# Обработчик команды /exit
@bot.message_handler(commands=['exit'])
@rate_limit_decorator('default')
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
            
            # Создаем клавиатуру с кнопками
            keyboard = create_queue_keyboard(queue_name)
            
            bot.reply_to(message, f"Вы успешно вышли из очереди '*{queue_name}*'.\n\n{queue_info}", parse_mode="Markdown", reply_markup=keyboard)
        else:
            bot.reply_to(message, f"Вы успешно вышли из очереди '{queue_name}'.\nОчередь теперь пуста.")
    
    except Exception as e:
        handle_error(message, e, "выходе из очереди")

# Обработчик команды /rejoin
@bot.message_handler(commands=['rejoin'])
@rate_limit_decorator('default')
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
        
        # Создаем клавиатуру с кнопками
        keyboard = create_queue_keyboard(queue_name)
        
        bot.reply_to(message, f"Вы успешно переместились в конец очереди '*{queue_name}*'.\n\n{queue_info}", parse_mode="Markdown", reply_markup=keyboard)
    
    except Exception as e:
        handle_error(message, e, "перемещении в конец очереди")

# Обработчик команды /delete
@bot.message_handler(commands=['delete'])
@rate_limit_decorator('default')
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
        handle_error(message, e, "удалении очереди")

# Обработчик команды /view
@bot.message_handler(commands=['view'])
@rate_limit_decorator('default')
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
            
            # Создаем клавиатуру с кнопками
            keyboard = create_queue_keyboard(queue_name)
            
            bot.reply_to(message, queue_info, parse_mode="Markdown", reply_markup=keyboard)
    
    except Exception as e:
        handle_error(message, e, "просмотре очереди")

# Обработчик команды /setname
@bot.message_handler(commands=['setname'])
@rate_limit_decorator('default')
def set_custom_name(message):
    try:
        # Получаем текст после команды /setname
        command_parts = message.text.split(' ', 1)
        
        # Если после /setname ничего нет, сбрасываем имя на имя из Telegram
        if len(command_parts) < 2:
            user_id = message.from_user.id
            
            # Получаем имя пользователя из Telegram
            telegram_name = message.from_user.first_name
            if message.from_user.last_name:
                telegram_name += " " + message.from_user.last_name
            
            # Обновляем имя пользователя в базе данных
            db.update_user_display_name(user_id, telegram_name)
            
            bot.reply_to(message, f"Ваше имя сброшено на стандартное из Telegram: '{telegram_name}'!")
            return
        
        new_name = command_parts[1].strip()
        user_id = message.from_user.id
        
        # Обновляем имя пользователя в базе данных
        db.update_user_display_name(user_id, new_name)
        
        bot.reply_to(message, f"Ваше имя успешно изменено на '{new_name}'!")
    
    except Exception as e:
        handle_error(message, e, "изменении имени")

# Вспомогательная функция для форматирования вывода очереди
def format_queue_info(queue_name, queue_id):
    # Получаем информацию о создателе очереди
    creator_name = db.get_queue_creator(queue_id)
    
    # Получаем список участников очереди
    queue_members = db.get_queue_members(queue_id)
    
    if not queue_members:
        return f"Очередь '*{queue_name}*' пуста.\nСоздатель: _{creator_name}_"
    
    # Ограничиваем количество участников для отображения
    max_members_to_show = 50
    total_members = len(queue_members)
    
    if total_members > max_members_to_show:
        queue_members = queue_members[:max_members_to_show]
    
    # Экранируем специальные символы в именах пользователей
    queue_list = []
    for name, username, order, _ in queue_members:
        # Экранируем специальные символы в имени
        safe_name = name.replace('*', '\\*').replace('_', '\\_').replace('`', '\\`').replace('[', '\\[')
        
        if username:
            # Экранируем специальные символы в username
            safe_username = username.replace('*', '\\*').replace('_', '\\_').replace('`', '\\`').replace('[', '\\[')
            queue_list.append(f"{order}. {safe_name} (@{safe_username})")
        else:
            queue_list.append(f"{order}. {safe_name}")
    
    # Соединяем список в строку
    queue_list_text = "\n".join(queue_list)
    
    # Экранируем специальные символы в имени создателя
    safe_creator_name = creator_name.replace('*', '\\*').replace('_', '\\_').replace('`', '\\`').replace('[', '\\[')
    
    result = f"Очередь '*{queue_name}*'\nСоздатель: _{safe_creator_name}_\nКоличество участников: {total_members}"
    
    if total_members > max_members_to_show:
        result += f"\n\nПоказаны первые {max_members_to_show} из {total_members} участников:\n\n{queue_list_text}"
    else:
        result += f"\n\n{queue_list_text}"
    
    return result

# Вспомогательная функция для обновления информации о пользователе
def update_user_info(user_id, username, first_name, last_name):
    # Получаем текущую информацию о пользователе
    current_username, display_name = db.get_user_info(user_id)
    
    # Если пользователь уже существует в базе, не обновляем его имя
    if display_name:
        # Обновляем только username, если он изменился
        if current_username != username:
            db.cursor.execute("UPDATE Users SET username = ? WHERE user_id = ?", (username, user_id))
            db.connection.commit()
    else:
        # Если пользователя нет в базе, добавляем его с именем из Telegram
        display_name = first_name
        if last_name:
            display_name += " " + last_name
        db.add_or_update_user(user_id, username, display_name)

# Функция для остановки бота
def stop_bot():
    global bot_running
    logger.info("===== QueueMateBot stopping =====")
    bot_running = False
    # Останавливаем поллинг бота
    bot.stop_polling()
    logger.info("Bot stopped")
    logger.info("=======================================")

# Функция для чтения команд из консоли
def console_listener():
    global bot_running
    logger.info("Console interface started. Available commands: stop, exit, quit, status")
    
    # Проверяем, запущен ли бот через systemd
    is_systemd = os.environ.get('INVOCATION_ID') is not None or os.environ.get('JOURNAL_STREAM') is not None
    
    if is_systemd:
        logger.info("Running under systemd, console input disabled")
        # В режиме systemd просто ждем, пока бот не будет остановлен
        while bot_running:
            time.sleep(1)
        return
    
    # Обычный режим с чтением команд из консоли
    while bot_running:
        try:
            command = input().strip().lower()
            
            if command in ['stop', 'exit', 'quit']:
                logger.info("Stop command received from console")
                stop_bot()
                break
            elif command == 'status':
                logger.info(f"Bot status: {'running' if bot_running else 'stopped'}")
                print(f"Bot status: {'running' if bot_running else 'stopped'}")
            elif command == 'help':
                print("Available commands:")
                print("  stop, exit, quit - stop the bot")
                print("  status - check bot status")
                print("  help - show this help message")
            else:
                print(f"Unknown command: {command}")
                print("Type 'help' to see available commands")
        except EOFError:
            # Обработка ситуации, когда стандартный ввод недоступен
            logger.warning("Standard input not available, console interface disabled")
            break
        except Exception as e:
            logger.error(f"Error in console interface: {str(e)}", exc_info=True)
    
    logger.info("Console interface stopped")

# Обработчик нажатий на инлайн-кнопки
@bot.callback_query_handler(func=lambda call: True)
def handle_callback_query(call):
    try:
        # Получаем данные из callback
        data = call.data
        chat_id = call.message.chat.id
        user_id = call.from_user.id
        
        # Проверяем ограничение для callback-запросов
        # Для присоединения к очереди используем специальный тип ограничения
        if data.startswith('join_'):
            is_limited, wait_time = check_rate_limit(user_id, 'join')
        else:
            is_limited, wait_time = check_rate_limit(user_id, 'default')
        
        if is_limited:
            logger.warning(f"Rate limit exceeded for user {user_id} in callback query")
            try:
                safe_answer_callback_query(call.id, f"Пожалуйста, не нажимайте кнопки слишком часто. Подождите {wait_time} сек.")
            except Exception as e:
                logger.error(f"Failed to send rate limit message via callback: {str(e)}")
            return
        
        # Обновляем информацию о пользователе
        update_user_info(user_id, call.from_user.username, call.from_user.first_name, call.from_user.last_name)
        
        # Обрабатываем callback для присоединения к очереди
        if data.startswith('join_'):
            queue_name = data[5:]  # Получаем название очереди
            
            # Получаем ID очереди
            queue_id = db.get_queue_id(queue_name, chat_id)
            if not queue_id:
                try:
                    safe_answer_callback_query(call.id, f"Очередь '{queue_name}' не найдена.")
                    return
                except Exception as e:
                    logger.error(f"Error answering callback query: {str(e)}")
                    return
            
            # Проверяем, состоит ли пользователь уже в очереди
            if db.check_user_in_queue(queue_id, user_id):
                try:
                    safe_answer_callback_query(call.id, f"Вы уже состоите в очереди '{queue_name}'.")
                    return
                except Exception as e:
                    logger.error(f"Error answering callback query: {str(e)}")
                    return
            
            # Добавляем пользователя в очередь
            try:
                db.add_user_to_queue(queue_id, user_id)
                safe_answer_callback_query(call.id, f"Вы присоединились к очереди '{queue_name}'.")
            except Exception as e:
                logger.error(f"Error adding user to queue: {str(e)}")
                try:
                    safe_answer_callback_query(call.id, f"Ошибка при присоединении к очереди: {str(e)}")
                except Exception:
                    logger.error("Failed to send error message via callback")
                return
            
            # Обновляем сообщение с очередью
            queue_info = format_queue_info(queue_name, queue_id)
            keyboard = create_queue_keyboard(queue_name)
            
            try:
                safe_edit_message_text(
                    chat_id=chat_id,
                    message_id=call.message.message_id,
                    text=queue_info,
                    parse_mode="Markdown",
                    reply_markup=keyboard
                )
            except telebot.apihelper.ApiTelegramException as api_error:
                # Игнорируем ошибку "message is not modified"
                if "message is not modified" in str(api_error):
                    pass
                else:
                    logger.error(f"Error updating message: {str(api_error)}")
        
        # Обрабатываем callback для выхода из очереди
        elif data.startswith('exit_'):
            queue_name = data[5:]  # Получаем название очереди
            
            # Получаем ID очереди
            queue_id = db.get_queue_id(queue_name, chat_id)
            if not queue_id:
                try:
                    safe_answer_callback_query(call.id, f"Очередь '{queue_name}' не найдена.")
                    return
                except Exception as e:
                    logger.error(f"Error answering callback query: {str(e)}")
                    return
            
            # Проверяем, состоит ли пользователь в очереди
            user_order = None
            for _, _, order, uid in db.get_queue_members(queue_id):
                if uid == user_id:
                    user_order = order
                    break
            
            if not user_order:
                try:
                    safe_answer_callback_query(call.id, f"Вы не состоите в очереди '{queue_name}'.")
                    return
                except Exception as e:
                    logger.error(f"Error answering callback query: {str(e)}")
                    return
            
            # Удаляем пользователя из очереди
            try:
                db.remove_user_from_queue(queue_id, user_id, user_order)
                safe_answer_callback_query(call.id, f"Вы вышли из очереди '{queue_name}'.")
            except Exception as e:
                logger.error(f"Error removing user from queue: {str(e)}")
                try:
                    safe_answer_callback_query(call.id, f"Ошибка при выходе из очереди: {str(e)}")
                except Exception:
                    logger.error("Failed to send error message via callback")
                return
            
            # Обновляем сообщение с очередью
            queue_info = format_queue_info(queue_name, queue_id)
            keyboard = create_queue_keyboard(queue_name)
            
            try:
                safe_edit_message_text(
                    chat_id=chat_id,
                    message_id=call.message.message_id,
                    text=queue_info,
                    parse_mode="Markdown",
                    reply_markup=keyboard
                )
            except telebot.apihelper.ApiTelegramException as api_error:
                # Игнорируем ошибку "message is not modified"
                if "message is not modified" in str(api_error):
                    pass
                else:
                    logger.error(f"Error updating message: {str(api_error)}")
    
    except Exception as e:
        # Сокращаем текст ошибки, чтобы избежать MESSAGE_TOO_LONG
        error_msg = str(e)
        if len(error_msg) > 50:
            error_msg = error_msg[:47] + "..."
            
        try:
            safe_answer_callback_query(call.id, f"Ошибка: {error_msg}")
        except Exception as callback_error:
            logger.error(f"Error answering callback query about error: {str(callback_error)}")

# Функция для периодической очистки словарей использования команд
def cleanup_command_usage():
    """
    Периодически очищает словари использования команд от устаревших записей.
    """
    while bot_running:
        try:
            current_time = time.time()
            
            # Очищаем словарь обычных команд
            for user_id in list(command_usage.keys()):
                while command_usage[user_id] and current_time - command_usage[user_id][0] > RATE_LIMITS['default']['period']:
                    command_usage[user_id].popleft()
                if not command_usage[user_id]:
                    del command_usage[user_id]
            
            # Очищаем словарь присоединений к очереди
            for user_id in list(join_queue_usage.keys()):
                while join_queue_usage[user_id] and current_time - join_queue_usage[user_id][0] > RATE_LIMITS['join']['period']:
                    join_queue_usage[user_id].popleft()
                if not join_queue_usage[user_id]:
                    del join_queue_usage[user_id]
            
            # Очищаем словарь групповых чатов
            for chat_id in list(chat_command_usage.keys()):
                while chat_command_usage[chat_id] and current_time - chat_command_usage[chat_id][0] > RATE_LIMITS['chat']['period']:
                    chat_command_usage[chat_id].popleft()
                if not chat_command_usage[chat_id]:
                    del chat_command_usage[chat_id]
            
            # Логируем статистику использования
            logger.debug(f"Command usage stats: users={len(command_usage)}, joins={len(join_queue_usage)}, chats={len(chat_command_usage)}")
            
        except Exception as e:
            logger.error(f"Error in cleanup_command_usage: {str(e)}")
        
        # Запускаем очистку каждые 5 минут
        time.sleep(300)

# Функция для запуска бота
def start_bot():
    global bot_running
    bot_running = True
    
    logger.info("===== QueueMateBot started =====")
    logger.info(f"Bot name: {bot.get_me().first_name}")
    logger.info(f"Bot username: @{bot.get_me().username}")
    logger.info(f"Bot ID: {bot.get_me().id}")
    logger.info("====================================")
    
    # Проверяем, запущен ли бот через systemd
    is_systemd = os.environ.get('INVOCATION_ID') is not None or os.environ.get('JOURNAL_STREAM') is not None
    
    # Запускаем поток для чтения команд из консоли, если не запущен через systemd
    if not is_systemd:
        console_thread = threading.Thread(target=console_listener, daemon=True)
        console_thread.start()
        logger.info("Console interface started")
    else:
        logger.info("Running under systemd, console interface disabled")
    
    # Запускаем поток для очистки словарей использования команд
    cleanup_thread = threading.Thread(target=cleanup_command_usage, daemon=True)
    cleanup_thread.start()
    logger.info("Command usage cleanup thread started")
    
    try:
        # Запускаем бота с увеличенным интервалом между запросами
        bot.polling(none_stop=True, interval=3, timeout=30)
    except Exception as e:
        logger.error(f"Error during bot operation: {str(e)}", exc_info=True)
    finally:
        bot_running = False
        logger.info("Bot has finished working")
    
    return bot

# Обработчик команды /remove - удаление пользователя из очереди администратором
@bot.message_handler(commands=['remove'])
@rate_limit_decorator('default')
def remove_user_admin(message):
    try:
        # Получаем текст после команды /remove
        command_parts = message.text.split(' ', 2)
        
        # Проверяем, указаны ли все необходимые параметры
        if len(command_parts) < 3:
            bot.reply_to(message, "Пожалуйста, укажите название очереди и имя пользователя или @username. Пример: `/remove Математика @username` или `/remove Математика Иван`", parse_mode="Markdown")
            return
        
        queue_name = command_parts[1].strip()
        user_identifier = command_parts[2].strip()
        chat_id = message.chat.id
        admin_id = message.from_user.id
        
        # Проверяем, является ли пользователь администратором или создателем чата
        chat_member = bot.get_chat_member(chat_id, admin_id)
        if chat_member.status not in ['administrator', 'creator']:
            bot.reply_to(message, "Только администраторы могут удалять пользователей из очереди.")
            return
        
        # Проверяем существование очереди
        queue_id = db.get_queue_id(queue_name, chat_id)
        if not queue_id:
            bot.reply_to(message, f"Очередь '{queue_name}' не найдена в этом чате.")
            return
        
        # Получаем список участников очереди
        queue_members = db.get_queue_members(queue_id)
        if not queue_members:
            bot.reply_to(message, f"Очередь '{queue_name}' пуста.")
            return
        
        # Ищем пользователя по идентификатору (имя или @username)
        user_found = False
        user_id = None
        user_order = None
        user_name = None
        
        for name, username, order, uid in queue_members:
            # Проверяем совпадение по username (если указан с @ или без)
            if username and (user_identifier.lower() == username.lower() or 
                            user_identifier.lower() == f"@{username}".lower()):
                user_found = True
                user_id = uid
                user_order = order
                user_name = name
                break
            
            # Проверяем совпадение по имени
            if name.lower() == user_identifier.lower():
                user_found = True
                user_id = uid
                user_order = order
                user_name = name
                break
        
        if not user_found:
            bot.reply_to(message, f"Пользователь '{user_identifier}' не найден в очереди '{queue_name}'.")
            return
        
        # Удаляем пользователя из очереди
        db.remove_user_from_queue(queue_id, user_id, user_order)
        
        # Формируем сообщение с обновленной информацией об очереди
        queue_info = format_queue_info(queue_name, queue_id)
        
        bot.reply_to(message, f"Пользователь '{user_name}' удален из очереди '{queue_name}'.\n\n{queue_info}", parse_mode="Markdown")
        logger.info(f"Admin {admin_id} removed user {user_id} ({user_name}) from queue '{queue_name}'")
    
    except Exception as e:
        handle_error(message, e, "удалении пользователя из очереди")

# Обработчик команды /setposition - установка позиции участника в очереди
@bot.message_handler(commands=['setposition'])
@rate_limit_decorator('default')
def set_user_position(message):
    try:
        # Получаем текст после команды /setposition
        command_parts = message.text.split(' ', 3)
        
        # Проверяем, указаны ли все необходимые параметры
        if len(command_parts) < 4:
            bot.reply_to(message, "Пожалуйста, укажите название очереди, имя пользователя или @username и новую позицию. Пример: `/setposition Математика @username 1` или `/setposition Математика Иван 3`", parse_mode="Markdown")
            return
        
        queue_name = command_parts[1].strip()
        user_identifier = command_parts[2].strip()
        
        # Проверяем, что новая позиция - число
        try:
            new_position = int(command_parts[3].strip())
            if new_position < 1:
                bot.reply_to(message, "Позиция должна быть положительным числом.")
                return
        except ValueError:
            bot.reply_to(message, "Позиция должна быть числом.")
            return
        
        chat_id = message.chat.id
        admin_id = message.from_user.id
        
        # Проверяем, является ли пользователь администратором или создателем чата
        chat_member = bot.get_chat_member(chat_id, admin_id)
        if chat_member.status not in ['administrator', 'creator']:
            bot.reply_to(message, "Только администраторы могут изменять позиции участников в очереди.")
            return
        
        # Проверяем существование очереди
        queue_id = db.get_queue_id(queue_name, chat_id)
        if not queue_id:
            bot.reply_to(message, f"Очередь '{queue_name}' не найдена в этом чате.")
            return
        
        # Получаем список участников очереди
        queue_members = db.get_queue_members(queue_id)
        if not queue_members:
            bot.reply_to(message, f"Очередь '{queue_name}' пуста.")
            return
        
        # Проверяем, что новая позиция не превышает количество участников
        if new_position > len(queue_members):
            bot.reply_to(message, f"Позиция не может быть больше количества участников ({len(queue_members)}).")
            return
        
        # Ищем пользователя по идентификатору (имя или @username)
        user_found = False
        user_id = None
        user_order = None
        user_name = None
        
        for name, username, order, uid in queue_members:
            # Проверяем совпадение по username (если указан с @ или без)
            if username and (user_identifier.lower() == username.lower() or 
                            user_identifier.lower() == f"@{username}".lower()):
                user_found = True
                user_id = uid
                user_order = order
                user_name = name
                break
            
            # Проверяем совпадение по имени
            if name.lower() == user_identifier.lower():
                user_found = True
                user_id = uid
                user_order = order
                user_name = name
                break
        
        if not user_found:
            bot.reply_to(message, f"Пользователь '{user_identifier}' не найден в очереди '{queue_name}'.")
            return
        
        # Если текущая позиция совпадает с новой, ничего не делаем
        if user_order == new_position:
            bot.reply_to(message, f"Пользователь '{user_name}' уже находится на позиции {new_position}.")
            return
        
        # Изменяем позицию пользователя в очереди
        with db.db_lock:
            # Временно удаляем пользователя из очереди
            db.cursor.execute("DELETE FROM QueueMembers WHERE queue_id = ? AND user_id = ?", 
                            (queue_id, user_id))
            
            # Если перемещаем вверх (на меньшую позицию)
            if new_position < user_order:
                db.cursor.execute("""
                    UPDATE QueueMembers 
                    SET join_order = join_order + 1 
                    WHERE queue_id = ? AND join_order >= ? AND join_order < ?
                """, (queue_id, new_position, user_order))
            # Если перемещаем вниз (на большую позицию)
            else:
                db.cursor.execute("""
                    UPDATE QueueMembers 
                    SET join_order = join_order - 1 
                    WHERE queue_id = ? AND join_order > ? AND join_order <= ?
                """, (queue_id, user_order, new_position))
            
            # Добавляем пользователя на новую позицию
            db.cursor.execute("INSERT INTO QueueMembers (queue_id, user_id, join_order) VALUES (?, ?, ?)", 
                            (queue_id, user_id, new_position))
            
            db.connection.commit()
        
        # Формируем сообщение с обновленной информацией об очереди
        queue_info = format_queue_info(queue_name, queue_id)
        
        bot.reply_to(message, f"Пользователь '{user_name}' перемещен на позицию {new_position} в очереди '{queue_name}'.\n\n{queue_info}", parse_mode="Markdown")
        logger.info(f"Admin {admin_id} moved user {user_id} ({user_name}) to position {new_position} in queue '{queue_name}'")
    
    except Exception as e:
        handle_error(message, e, "изменении позиции пользователя") 