# QueueMateBot

Телеграм-бот для управления очередями в групповых чатах.

## Описание

QueueMateBot позволяет создавать и управлять очередями в групповых чатах Telegram. Бот помогает организовать порядок выступлений, ответов на вопросы или любых других действий, требующих очереди.

## Функциональность

- Создание очередей (только администраторы)
- Присоединение к очереди
- Выход из очереди
- Просмотр списка очередей
- Просмотр участников конкретной очереди
- Удаление очередей (только администраторы)
- Установка отображаемого имени

## Структура проекта

- `main.py` - основной файл для запуска бота
- `config.py` - конфигурация бота и базы данных
- `database.py` - работа с базой данных
- `handlers.py` - обработчики команд

## Установка и запуск

1. Установите необходимые зависимости:
```
pip install pyTelegramBotAPI
```

2. Настройте токен бота в файле `config.py`

3. Запустите бота:
```
python main.py
```

## Команды бота

- `/start` - начало работы с ботом
- `/help` - список доступных команд
- `/create [название]` - создать новую очередь (только для администраторов)
- `/join [название]` - присоединиться к очереди
- `/exit [название]` - выйти из очереди
- `/view` - показать список всех очередей в чате
- `/view [название]` - показать участников конкретной очереди
- `/delete [название]` - удалить очередь (только для администраторов)
- `/setname [имя]` - установить своё отображаемое имя

## Примеры использования

- `/create Математика` - создать очередь "Математика"
- `/join Математика` - встать в очередь "Математика"
- `/exit Математика` - выйти из очереди "Математика"
- `/view` - посмотреть все очереди
- `/view Математика` - посмотреть очередь "Математика"
- `/delete Математика` - удалить очередь "Математика"
- `/setname Иван` - установить имя "Иван"
