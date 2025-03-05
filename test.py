import telebot

bot = telebot.TeleBot('7365658286:AAGQ7Ob2FUAH1Vpc0oLSrZebKth7xZ2M3e0')

# Обработчик команды /start
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "Привет! Я тестовый бот. Как дела?")
    
@bot.message_handler(commands=['info'])
def send_welcome(message):
    bot.reply_to(message, message)

# Обработчик упоминаний бота в группе
@bot.message_handler(func=lambda message: message.text and '@QueueMateBot' in message.text)
def handle_mention(message):
    bot.reply_to(message, "Вы упомянули меня! Чем могу помочь?")

# Обработчик всех сообщений (если бот администратор)
@bot.message_handler(func=lambda message: True)
def echo_all(message):
    if message.chat.type in ['group', 'supergroup']:
        bot.reply_to(message, f"Вы написали: {message.text}")

# Запуск бота
bot.polling()