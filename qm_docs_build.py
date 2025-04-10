#!/usr/bin/env python
"""
Модуль для сборки документации QueueMateBot с помощью MkDocs.
Используется для запуска через консольную команду queuematebot-docs.
"""

import subprocess
import sys

def build_docs():
    """Функция для вызова сборки документации из командной строки"""
    try:
        print("Сборка документации с помощью MkDocs...")
        subprocess.check_call(['mkdocs', 'build', '--clean'])
        print("Документация успешно собрана в директории 'site/'")
    except Exception as e:
        print(f"Ошибка при сборке документации: {e}")
        return 1
    return 0

def serve_docs():
    """Функция для запуска сервера документации в режиме разработки"""
    try:
        print("Запуск сервера документации MkDocs...")
        subprocess.call(['mkdocs', 'serve'])
    except Exception as e:
        print(f"Ошибка при запуске сервера документации: {e}")
        return 1
    return 0

def main():
    """Основная функция для консольной команды"""
    if len(sys.argv) > 1 and sys.argv[1] == 'serve':
        return serve_docs()
    return build_docs()

if __name__ == "__main__":
    sys.exit(main()) 