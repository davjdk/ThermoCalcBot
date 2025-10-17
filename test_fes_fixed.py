"""Тестирование случая с FeS для проверки отбора фаз по температуре плавления."""

import asyncio
import sys
from pathlib import Path

# Добавляем src в путь
src_path = Path(__file__).parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

# Импортируем create_orchestrator из main
from main import create_orchestrator


async def main():
    """Тестовый запуск для случая CaO + FeS."""

    orchestrator = create_orchestrator()

    # Запрос из логов
    query = "Возможно ли взаимодействие оксида кальция и сульфида железа при 600 - 1200 цельсия?"

    print("=" * 80)
    print("ТЕСТ: Проверка отбора фаз для FeS")
    print("=" * 80)
    print(f"Запрос: {query}")
    print("=" * 80)
    print()

    try:
        result = await orchestrator.process_query(query)
        print(result)
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
