import os

# Токен бота Telegram
# В идеале токен должен храниться в переменных окружения
# BOT_TOKEN = os.environ.get('BOT_TOKEN')
BOT_TOKEN = '7365658286:AAGQ7Ob2FUAH1Vpc0oLSrZebKth7xZ2M3e0'

# Настройки базы данных
DB_NAME = 'botdb.db'

# Сообщения бота
MESSAGES = {
    'welcome': """
Привет! Я QueueMateBot - бот для управления очередями в групповых чатах.

Добавьте меня в группу и используйте команду `/help`, чтобы узнать, как создавать очереди и управлять ими.
""",
    'help': """
📋 *Список доступных команд:*

*Основные команды:*
`/view` - показать список всех очередей в чате
`/view [название]` - показать участников конкретной очереди
`/join [название]` - присоединиться к очереди
`/exit [название]` - выйти из очереди
`/rejoin [название]` - переместиться в конец очереди
`/setname [имя]` - установить своё отображаемое имя
`/setname` - сбросить имя на стандартное из Telegram

*Команды администраторов:*
`/create [название]` - создать новую очередь
`/delete [название]` - удалить очередь полностью
`/remove [название] [пользователь]` - удалить пользователя из очереди
`/setposition [название] [пользователь] [позиция]` - изменить позицию пользователя в очереди
"""
} 