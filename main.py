import logging
import atexit
from database import init_database, close_connection
from handlers import start_bot

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Регистрируем функцию закрытия соединения с базой данных при завершении работы
atexit.register(close_connection)

if __name__ == "__main__":
    try:
        logger.info("Initializing database...")
        init_database()
        logger.info("Starting bot...")
        start_bot()
        logger.info("Bot started successfully")
    except Exception as e:
        logger.error(f"Error starting bot: {str(e)}", exc_info=True) 