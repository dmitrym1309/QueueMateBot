import telebot
import sqlite3
import threading
import time
from config import BOT_TOKEN, MESSAGES
import database as db
import logging

# Настройка логирования
logger = logging.getLogger(__name__)
from telebot import types  # Добавляем импорт для работы с кнопками

# Создаем экземпляр бота
bot = telebot.TeleBot(BOT_TOKEN)

# Глобальная переменная для контроля работы бота
bot_running = True

# Функция для обработки ошибок
def handle_error(message, error, operation):
    error_text = str(error)
    logger.error(f"Error during {operation}: {error_text}", exc_info=True)
    bot.reply_to(message, f"Произошла ошибка при {operation}: {error_text}")

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
    
    # Ограничиваем количество участников для отображения, чтобы избежать MESSAGE_TOO_LONG
    max_members_to_show = 50
    total_members = len(queue_members)
    
    if total_members > max_members_to_show:
        queue_members = queue_members[:max_members_to_show]
        
    # Формируем сообщение со списком участников без моноширинного шрифта для чисел
    queue_list = "\n".join([
        f"{order}. {name} (@{username})" if username else f"{order}. {name}"
        for name, username, order, _ in queue_members
    ])
    
    result = f"Очередь '*{queue_name}*'\nСоздатель: _{creator_name}_\nКоличество участников: {total_members}"
    
    if total_members > max_members_to_show:
        result += f"\n\nПоказаны первые {max_members_to_show} из {total_members} участников:\n\n{queue_list}"
    else:
        result += f"\n\n{queue_list}"
        
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
    
    # Формируем сообщение со списком участников с использованием list comprehension
    queue_list = "\n".join(
        f"{order}. {name}" + (f" (@{username})" if username else "")
        for name, username, order, _ in queue_members
    )
    
    return f"Очередь '*{queue_name}*'\nСоздатель: _{creator_name}_\nКоличество участников: {len(queue_members)}\n\n{queue_list}"

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
        except Exception as e:
            logger.error(f"Error in console interface: {str(e)}", exc_info=True)
    
    logger.info("Console interface stopped")
# Обработчик нажатий на инлайн-кнопки
@bot.callback_query_handler(func=lambda call: True)
def handle_callback_query(call):
    try:
        # Получаем данные из callback_data
        data = call.data.split('_', 1)
        action = data[0]
        queue_name = data[1]
        
        chat_id = call.message.chat.id
        user_id = call.from_user.id
        
        # Добавляем пользователя в базу данных
        user_name = call.from_user.username or ""
        update_user_info(user_id, user_name, call.from_user.first_name, call.from_user.last_name)
        
        # Проверяем существование очереди
        queue_id = db.get_queue_id(queue_name, chat_id)
        if not queue_id:
            bot.answer_callback_query(call.id, f"Очередь '{queue_name}' не найдена в этом чате.")
            return
        
        # Обрабатываем действие в зависимости от нажатой кнопки
        if action == "join":
            # Проверяем, не состоит ли пользователь уже в этой очереди
            if db.check_user_in_queue(queue_id, user_id):
                bot.answer_callback_query(call.id, f"Вы уже состоите в очереди '{queue_name}'.")
                return
            
            # Добавляем пользователя в очередь
            db.add_user_to_queue(queue_id, user_id)
            bot.answer_callback_query(call.id, f"Вы успешно присоединились к очереди '{queue_name}'!")
            
        elif action == "exit":
            # Проверяем, состоит ли пользователь в этой очереди
            user_order = db.check_user_in_queue(queue_id, user_id)
            if not user_order:
                bot.answer_callback_query(call.id, f"Вы не состоите в очереди '{queue_name}'.")
                return
            
            # Удаляем пользователя из очереди
            db.remove_user_from_queue(queue_id, user_id, user_order)
            bot.answer_callback_query(call.id, f"Вы успешно вышли из очереди '{queue_name}'.")
            
        elif action == "rejoin":
            # Проверяем, состоит ли пользователь в этой очереди
            user_order = db.check_user_in_queue(queue_id, user_id)
            if not user_order:
                bot.answer_callback_query(call.id, f"Вы не состоите в очереди '{queue_name}'. Сначала присоединитесь.")
                return
            
            # Перемещаем пользователя в конец очереди
            db.rejoin_queue(queue_id, user_id)
            bot.answer_callback_query(call.id, f"Вы успешно переместились в конец очереди '{queue_name}'.")
        
        # Обновляем сообщение с очередью
        queue_info = format_queue_info(queue_name, queue_id)
        keyboard = create_queue_keyboard(queue_name)
        
        try:
            bot.edit_message_text(
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
            # Если сообщение слишком длинное, отправляем новое сообщение
            elif "MESSAGE_TOO_LONG" in str(api_error):
                bot.send_message(
                    chat_id=chat_id,
                    text="Очередь слишком большая для отображения. Используйте команду /view для просмотра.",
                    reply_markup=keyboard
                )
            else:
                # Для других ошибок API отправляем короткое уведомление
                bot.answer_callback_query(call.id, "Не удалось обновить сообщение. Попробуйте еще раз.")
                
    except Exception as e:
        # Сокращаем текст ошибки, чтобы избежать MESSAGE_TOO_LONG
        error_msg = str(e)
        if len(error_msg) > 50:
            error_msg = error_msg[:47] + "..."
            
        try:
            bot.answer_callback_query(call.id, f"Ошибка: {error_msg}")
        except:
            # Если даже это не работает, просто логируем ошибку
            import traceback
            error_details = traceback.format_exc()
            print(f"Ошибка в обработчике callback: {error_details}")

# Функция для запуска бота
def start_bot():
    global bot_running
    bot_running = True
    
    logger.info("===== QueueMateBot started =====")
    logger.info(f"Bot name: {bot.get_me().first_name}")
    logger.info(f"Bot username: @{bot.get_me().username}")
    logger.info(f"Bot ID: {bot.get_me().id}")
    logger.info("====================================")
    
    # Запускаем поток для чтения команд из консоли
    console_thread = threading.Thread(target=console_listener, daemon=True)
    console_thread.start()
    
    try:
        # Запускаем бота
        bot.polling(none_stop=True, interval=1)
    except Exception as e:
        logger.error(f"Error during bot operation: {str(e)}", exc_info=True)
    finally:
        bot_running = False
        logger.info("Bot has finished working")
    
    return bot 