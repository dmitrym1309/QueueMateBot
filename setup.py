from setuptools import setup, find_packages

setup(
    name="QueueMateBot",
    version="0.1.0",
    description="Телеграм-бот для управления очередями в групповых чатах",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    author="dmitrym1309 & stepanovvladislav",
    packages=find_packages(),
    py_modules=["main", "handlers", "database", "config"],
    install_requires=[
        "pyTelegramBotAPI==4.14.0",
        "python-dotenv==1.0.0",
    ],
    entry_points={
        'console_scripts': [
            'queuematebot=main:start_bot_wrapper',
        ],
    },
    python_requires='>=3.7',
) 