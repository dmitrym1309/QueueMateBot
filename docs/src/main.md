# Модуль main

Модуль main является точкой входа для QueueMateBot.

## Обзор

Этот модуль инициализирует логирование, запускает базу данных и основной цикл бота.

## Основные функции

### start_bot_wrapper()

Основная функция-обертка для запуска бота:
- Инициализирует базу данных
- Запускает бота
- Обрабатывает возможные исключения

```python
def start_bot_wrapper():
    try:
        logger.info("Initializing database...")
        init_database()
        logger.info("Starting bot...")
        start_bot()
    except Exception as e:
        logger.error(f"Error starting bot: {str(e)}", exc_info=True) 