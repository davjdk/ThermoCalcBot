"""
Тесты для функциональности предупреждений о высоких температурах.

Проверяют работу новых методов has_high_temperatures, has_extreme_temperatures
и collect_temperature_warnings.
"""

import pytest
from thermo_agents.models.search import DatabaseRecord, CompoundSearchResult


class TestTemperatureWarnings:
    """Тесты системы предупреждений о температурах."""

    def test_normal_temperatures_no_warnings(self):
        """TC1: Обычные температуры - нет предупреждений."""
        record = DatabaseRecord(
            formula="H2O",
            phase="l",
            tmin=298.0,
            tmax=500.0,
            h298=-285830.0,
            s298=69.95,
            f1=32.24,
            f2=1.923,
            f3=0.005341,
            f4=-0.00001512,
            f5=0.0,
            f6=0.0,
            tmelt=273.15,
            tboil=373.15,
            reliability_class=1
        )

        assert not record.has_high_temperatures()
        assert not record.has_extreme_temperatures()
        warnings = record.get_temperature_warnings()
        assert len(warnings) == 0

    def test_high_temperatures_warning(self):
        """TC2: Высокие температуры - должно быть предупреждение."""
        record = DatabaseRecord(
            formula="Ar",
            phase="g",
            tmin=298.0,
            tmax=60000.0,  # Высокая, но не экстремальная
            h298=0.0,
            s298=154.8,
            f1=20.786,
            f2=0.0,
            f3=0.0,
            f4=0.0,
            f5=0.0,
            f6=0.0,
            tmelt=83.8,
            tboil=87.3,
            reliability_class=1
        )

        assert record.has_high_temperatures()
        assert not record.has_extreme_temperatures()
        warnings = record.get_temperature_warnings()
        assert len(warnings) == 1
        assert "Высокая температура" in warnings[0]
        assert "60000K" in warnings[0]

    def test_extreme_temperatures_warning(self):
        """TC3: Экстремальные температуры - должно быть предупреждение."""
        record = DatabaseRecord(
            formula="UF5",
            phase="g",
            tmin=298.0,
            tmax=120000.0,  # Экстремально высокая (>100000)
            h298=-1000000.0,
            s298=300.0,
            f1=50.0,
            f2=0.0,
            f3=0.0,
            f4=0.0,
            f5=0.0,
            f6=0.0,
            tmelt=1000.0,
            tboil=2000.0,
            reliability_class=1
        )

        assert record.has_high_temperatures()
        assert record.has_extreme_temperatures()
        warnings = record.get_temperature_warnings()
        assert len(warnings) == 1
        assert "Экстремально высокая температура" in warnings[0]
        assert "120000K" in warnings[0]

    def test_compound_search_result_collect_warnings(self):
        """TC4: Сбор предупреждений в CompoundSearchResult."""
        # Создаем записи с разными температурными режимами
        normal_record = DatabaseRecord(
            formula="H2O",
            phase="l",
            tmin=298.0,
            tmax=500.0,
            h298=-285830.0,
            s298=69.95,
            f1=32.24,
            f2=1.923,
            f3=0.005341,
            f4=-0.00001512,
            f5=0.0,
            f6=0.0,
            tmelt=273.15,
            tboil=373.15,
            reliability_class=1
        )

        high_record = DatabaseRecord(
            formula="Ar",
            phase="g",
            tmin=298.0,
            tmax=60000.0,
            h298=0.0,
            s298=154.8,
            f1=20.786,
            f2=0.0,
            f3=0.0,
            f4=0.0,
            f5=0.0,
            f6=0.0,
            tmelt=83.8,
            tboil=87.3,
            reliability_class=1
        )

        extreme_record = DatabaseRecord(
            formula="UF5",
            phase="g",
            tmin=298.0,
            tmax=120000.0,
            h298=-1000000.0,
            s298=300.0,
            f1=50.0,
            f2=0.0,
            f3=0.0,
            f4=0.0,
            f5=0.0,
            f6=0.0,
            tmelt=1000.0,
            tboil=2000.0,
            reliability_class=1
        )

        # Создаем результат поиска
        search_result = CompoundSearchResult(
            compound_formula="test_compound",
            records_found=[normal_record, high_record, extreme_record]
        )

        # Собираем предупреждения
        search_result.collect_temperature_warnings()

        # Проверяем результаты
        assert len(search_result.warnings) == 2  # Два разных типа предупреждений
        warning_texts = " ".join(search_result.warnings)

        # Должно быть предупреждение о высокой температуре
        assert "Высокая температура" in warning_texts
        assert "60000K" in warning_texts

        # Должно быть предупреждение об экстремальной температуре
        assert "Экстремально высокая температура" in warning_texts
        assert "120000K" in warning_texts

    def test_compound_search_result_duplicate_warnings(self):
        """TC5: Устранение дубликатов предупреждений."""
        # Создаем несколько записей с одинаковыми высокими температурами
        high_records = []
        for i in range(3):
            record = DatabaseRecord(
                formula=f"Ar{i}",
                phase="g",
                tmin=298.0,
                tmax=60000.0,  # Одинаковая высокая температура
                h298=0.0,
                s298=154.8,
                f1=20.786,
                f2=0.0,
                f3=0.0,
                f4=0.0,
                f5=0.0,
                f6=0.0,
                tmelt=83.8,
                tboil=87.3,
                reliability_class=1
            )
            high_records.append(record)

        search_result = CompoundSearchResult(
            compound_formula="test_compound",
            records_found=high_records
        )

        # Собираем предупреждения
        search_result.collect_temperature_warnings()

        # Должно быть только одно предупреждение со счетчиком
        assert len(search_result.warnings) == 1
        assert "(3 записей)" in search_result.warnings[0]
        assert "Высокая температура" in search_result.warnings[0]

    def test_temperature_threshold_boundary_values(self):
        """TC6: Проверка граничных значений порогов."""
        # Тест ниже HIGH_TEMP_THRESHOLD (50000K)
        below_boundary_record = DatabaseRecord(
            formula="test",
            phase="g",
            tmin=298.0,
            tmax=49999.0,  # Ниже границы
            h298=0.0,
            s298=100.0,
            f1=20.0,
            f2=0.0,
            f3=0.0,
            f4=0.0,
            f5=0.0,
            f6=0.0,
            tmelt=100.0,
            tboil=200.0,
            reliability_class=1
        )

        # Ниже границы не должно быть предупреждений
        assert not below_boundary_record.has_high_temperatures()
        assert not below_boundary_record.has_extreme_temperatures()
        warnings = below_boundary_record.get_temperature_warnings()
        assert len(warnings) == 0

        # Тест чуть выше HIGH_TEMP_THRESHOLD
        above_boundary_record = DatabaseRecord(
            formula="test2",
            phase="g",
            tmin=298.0,
            tmax=50001.0,  # Чуть выше границы
            h298=0.0,
            s298=100.0,
            f1=20.0,
            f2=0.0,
            f3=0.0,
            f4=0.0,
            f5=0.0,
            f6=0.0,
            tmelt=100.0,
            tboil=200.0,
            reliability_class=1
        )

        # Чуть выше границы должно быть предупреждение
        assert above_boundary_record.has_high_temperatures()
        assert not above_boundary_record.has_extreme_temperatures()
        warnings = above_boundary_record.get_temperature_warnings()
        assert len(warnings) == 1
        assert "Высокая температура" in warnings[0]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])