"""Главный файл запуска термодинамической системы."""

import asyncio
import os
import sys
from pathlib import Path

# Устанавливаем кодировку для Windows
if sys.platform == "win32":
    import codecs

    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())
    sys.stderr = codecs.getwriter("utf-8")(sys.stderr.detach())

# Добавляем src в путь
src_path = Path(__file__).parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from dotenv import load_dotenv

from thermo_agents.orchestrator_multi_phase import (
    MultiPhaseOrchestrator,
    MultiPhaseOrchestratorConfig
)

# Загрузка переменных окружения
load_dotenv()


def create_orchestrator(db_path: str = "data/thermo_data.db") -> MultiPhaseOrchestrator:
    """
    Создание и настройка многофазного оркестратора термодинамической системы.

    Args:
        db_path: Путь к файлу базы данных

    Returns:
        Настроенный MultiPhaseOrchestrator с поддержкой многофазных расчётов
    """
    # Конфигурация многофазного оркестратора
    config = MultiPhaseOrchestratorConfig(
        db_path=db_path,
        llm_api_key=os.getenv("OPENROUTER_API_KEY", ""),
        llm_base_url=os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1"),
        llm_model=os.getenv("LLM_DEFAULT_MODEL", "openai/gpt-4o"),
        static_cache_dir="data/static_compounds",
        integration_points=100,  # Точность численного интегрирования
    )

    # Создание оркестратора
    orchestrator = MultiPhaseOrchestrator(config)

    return orchestrator


async def main_interactive():
    """Главная функция в режиме ожидания запросов пользователя."""
    # Инициализация
    db_path = Path(__file__).parent / "data" / "thermo_data.db"
    orchestrator: MultiPhaseOrchestrator = create_orchestrator(str(db_path))

    print("\nТермодинамическая система v2.0")
    print("Гибридная архитектура: LLM + детерминированная логика\n")

    try:
        while True:
            # Ожидание запроса
            query = input("Введите запрос: ").strip()

            if not query:
                continue

            print()

            try:
                # Обработка запроса
                response = await orchestrator.process_query(query)

  # Логирование упрощено в многофазной архитектуре

                print(response)
                print()
            except Exception as e:
                print(f"Ошибка обработки: {e}\n")

                # Логирование ошибок упрощено в многофазной архитектуре

    except KeyboardInterrupt:
        print("\n\nЗавершение работы...")
    except Exception as e:
        print(f"\nКритическая ошибка: {e}")
    finally:
        # Многофазный оркестратор не требует shutdown()
        pass


async def main_test():
    """Тестовый режим с предопределённым запросом."""
    # Инициализация
    db_path = Path(__file__).parent / "data" / "thermo_data.db"
    orchestrator: MultiPhaseOrchestrator = create_orchestrator(str(db_path))

    # Логирование упрощено в многофазной архитектуре

    print("\n" + "=" * 80)
    print("Термодинамическая система v2.0 - ТЕСТОВЫЙ РЕЖИМ")
    print("=" * 80)

    # Тестовый запрос
    test_query = "Реагирует ли сероводород с оксидом железа(III) при температуре 500–700 °C??"

    # Логирование упрощено в многофазной архитектуре

    try:
        # Обработка запроса
        response = await orchestrator.process_query(test_query)

        # Логирование упрощено в многофазной архитектуре

        # Убираем эмодзи и Unicode символы для совместимости с Windows
        response_clean = response.replace("✅", "[OK]").replace("❌", "[ОШИБКА]")
        response_clean = response_clean.replace("⚠️", "[ВНИМАНИЕ]").replace(
            "📊", "[ДАННЫЕ]"
        )
        response_clean = response_clean.replace("💡", "[СОВЕТ]")
        # Дополнительная замена Unicode символов
        response_clean = response_clean.replace("→", "->")
        response_clean = response_clean.replace("°", " deg ")

        print("\n[РЕЗУЛЬТАТ]")
        print(response_clean)
        print("\n" + "=" * 80)
        print("[ТЕСТ ЗАВЕРШЁН УСПЕШНО]")
        print("=" * 80)

        # Логирование упрощено в многофазной архитектуре

    except Exception as e:
        print(f"\n[ОШИБКА] Ошибка обработки: {e}")
        import traceback

        # Логирование упрощено в многофазной архитектуре

        traceback.print_exc()
    finally:
        # Многофазный оркестратор не требует shutdown()
        pass


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Термодинамическая система v2.0",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  python main.py                    # Интерактивный режим (по умолчанию)
  python main.py --test             # Тестовый режим с предопределённым запросом
        """,
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Запустить тестовый режим с предопределённым запросом",
    )

    args = parser.parse_args()

    try:
        if args.test:
            # Тестовый режим
            asyncio.run(main_test())
        else:
            # Интерактивный режим (по умолчанию)
            asyncio.run(main_interactive())
    except KeyboardInterrupt:
        print("\n\nЗавершение работы пользователем")
    except Exception as e:
        print(f"\n[ОШИБКА] Критическая ошибка: {e}")
        import traceback

        traceback.print_exc()
        print(f"\n[ОШИБКА] Критическая ошибка: {e}")
        import traceback

        traceback.print_exc()
