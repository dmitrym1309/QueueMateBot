from setuptools import setup, find_packages
from setuptools.command.build_py import build_py
import subprocess
import os

class BuildDocsCommand(build_py):
    """Команда для сборки документации с помощью MkDocs"""
    def run(self):
        try:
            print("Сборка документации с помощью MkDocs...")
            subprocess.check_call(['mkdocs', 'build', '--clean'])
            print("Документация успешно собрана в директории 'site/'")
        except Exception as e:
            print(f"Ошибка при сборке документации: {e}")
        
        # Вызываем родительский метод для продолжения обычной сборки
        build_py.run(self)

def build_docs_cmd():
    """Функция для вызова сборки документации из командной строки"""
    try:
        subprocess.check_call(['mkdocs', 'build', '--clean'])
        print("Документация успешно собрана в директории 'site/'")
    except Exception as e:
        print(f"Ошибка при сборке документации: {e}")
        return 1
    return 0

setup(
    name="QueueMateBot",
    version="0.1.0",
    description="Телеграм-бот для управления очередями в групповых чатах",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    author="dmitrym1309 & stepanovvladislav",
    packages=find_packages(),
    py_modules=["main", "handlers", "database", "config", "qm_docs_build"],
    install_requires=[
        "pyTelegramBotAPI==4.14.0",
        "python-dotenv==1.0.0",
    ],
    extras_require={
        'docs': [
            'mkdocs==1.5.3',
            'mkdocs-material==9.4.14',
            'mkdocstrings==0.24.0',
            'mkdocstrings-python==1.7.5',
        ],
    },
    entry_points={
        'console_scripts': [
            'queuematebot=main:start_bot_wrapper',
            'queuematebot-docs=qm_docs_build:main',
        ],
    },
    cmdclass={
        'build_docs': BuildDocsCommand,
        'build_py': BuildDocsCommand,  # Заменяем стандартную команду build_py
    },
    python_requires='>=3.7',
) 