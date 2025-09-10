"""
AI Agents Project - Главный модуль
"""

import sys
from pathlib import Path


def main():
    """Основная функция приложения."""
    print("🤖 AI Agents Project")
    print(f"Python версия: {sys.version}")
    print(f"Рабочая директория: {Path.cwd()}")
    print("Проект готов к разработке AI агентов!")


if __name__ == "__main__":
    main()
