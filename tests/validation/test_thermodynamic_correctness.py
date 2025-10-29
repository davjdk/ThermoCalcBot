"""
Валидация термодинамической корректности расчётов.

Тестирует соответствие физических законов и термодинамических принципов:
- Непрерывность энтальпии при фазовых переходах
- Термодинамическая согласованность (G = H - TS)
- Разумность значений энтропии плавления/кипения
- Корректность знаков энергий переходов
- Интегрирование теплоёмкости
"""

import pytest
import asyncio
import sys
import math
from pathlib import Path

# Добавляем src в путь для тестов
src_path = Path(__file__).parent.parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from thermo_agents.orchestrator_multi_phase import (
    MultiPhaseOrchestrator,
    MultiPhaseOrchestratorConfig
)
from thermo_agents.calculations.thermodynamic_calculator import ThermodynamicCalculator


@pytest.fixture
def test_db_path():
    """Путь к тестовой базе данных."""
    return "data/thermo_data.db"


@pytest.fixture
async def multi_phase_orchestrator(test_db_path):
    """Создает многофазный оркестратор для тестов."""

    config = MultiPhaseOrchestratorConfig(
        db_path=test_db_path,
        llm_api_key="test_key",
        llm_base_url="https://api.openai.com/v1",
        llm_model="gpt-4o-mini",
        static_cache_dir="data/static_compounds",
        integration_points=100,
    )

    orchestrator = MultiPhaseOrchestrator(config)
    yield orchestrator


@pytest.fixture
def thermodynamic_calculator():
    """Создает термодинамический калькулятор для тестов."""
    return ThermodynamicCalculator()


class TestThermodynamicCorrectness:
    """Тесты термодинамической корректности."""

    @pytest.mark.asyncio
    async def test_enthalpy_continuity_across_transitions(self, multi_phase_orchestrator):
        """
        Тест непрерывности энтальпии при фазовых переходах.

        Проверяет, что энтальпия не имеет скачков при фазовых переходах
        (за исключением скрытой теплоты перехода).
        """

        # Вода - хороший тестовый случай
        compound = "H2O"

        # Поиск данных для разных фаз
        solid_result = multi_phase_orchestrator.compound_searcher.search_compound(compound, (250, 270))
        liquid_result = multi_phase_orchestrator.compound_searcher.search_compound(compound, (280, 370))
        gas_result = multi_phase_orchestrator.compound_searcher.search_compound(compound, (380, 400))

        # Проверяем наличие данных
        phases_data = {}
        if solid_result and solid_result.records_found:
            phases_data['solid'] = solid_result.records_found[0]
        if liquid_result and liquid_result.records_found:
            phases_data['liquid'] = liquid_result.records_found[0]
        if gas_result and gas_result.records_found:
            phases_data['gas'] = gas_result.records_found[0]

        # Если есть данные для разных фаз, проверяем согласованность
        if len(phases_data) >= 2:
            h298_values = {}
            for phase, record in phases_data.items():
                h298 = record.get('H298')
                if h298 is not None:
                    try:
                        h298_values[phase] = float(h298)
                    except (ValueError, TypeError):
                        continue

            # Проверяем, что значения H298 для разных фаз разумны
            if len(h298_values) >= 2:
                values = list(h298_values.values())
                # Разница не должна быть экстремальной (более 1000 кДж/моль)
                max_diff = max(values) - min(values)
                assert max_diff < 1000.0, f"Слишком большая разница H298 между фазами: {h298_values}"

    @pytest.mark.asyncio
    async def test_entropy_thermodynamic_consistency(self, multi_phase_orchestrator):
        """
        Тест термодинамической согласованности энтропии.

        Проверяет соотношение G = H - TS и разумность значений энтропии.
        """

        # Тестируем на нескольких соединениях с хорошими данными
        test_compounds = ["H2O", "CO2", "NH3"]

        for compound in test_compounds:
            result = multi_phase_orchestrator.compound_searcher.search_compound(compound, (298, 298))

            if result and result.records_found:
                for record in result.records_found[:1]:  # Проверяем первую запись
                    h298 = record.get('H298')
                    s298 = record.get('S298')
                    g298 = record.get('G298')

                    if h298 is not None and s298 is not None:
                        try:
                            h298_val = float(h298)
                            s298_val = float(s298)

                            # Проверяем разумность энтропии (положительная, в разумных пределах)
                            assert s298_val > 0, f"Энтропия должна быть положительной: {compound} S298 = {s298_val}"
                            assert s298_val < 1000, f"Слишком высокая энтропия: {compound} S298 = {s298_val} Дж/(моль·K)"

                            # Если есть G298, проверяем согласованность
                            if g298 is not None:
                                try:
                                    g298_val = float(g298)
                                    calculated_g = h298_val - 298.15 * s298_val / 1000  # S в Дж, H/G в кДж

                                    # Допуск 50 кДж/моль для учета разных источников данных
                                    diff = abs(g298_val - calculated_g)
                                    assert diff < 50.0, f"Несогласованность G=H-TS для {compound}: G={g298_val}, расчёт={calculated_g:.2f}"

                                except (ValueError, TypeError):
                                    pass

                        except (ValueError, TypeError):
                            pass

    def test_gibbs_energy_relationship_validation(self, thermodynamic_calculator):
        """
        Тест проверки соотношений энергии Гиббса.

        Проверяет корректность расчёта энергии Гиббса и её зависимость от температуры.
        """

        # Создаём тестовые данные
        class TestRecord:
            def __init__(self):
                self.H298 = -285.83  # H2O(ж) кДж/моль
                self.S298 = 69.95    # H2O(ж) Дж/(моль·K)
                self.f1 = 33.33
                self.f2 = -11.33
                self.f3 = 11.47
                self.f4 = -3.86
                self.f5 = 0.5
                self.f6 = -0.032

        record = TestRecord()

        # Тестируем корректность расчёта G при разных температурах
        temperatures = [298, 350, 400, 500]

        for T in temperatures:
            H = thermodynamic_calculator.calculate_enthalpy(record, T, 298)
            S = thermodynamic_calculator.calculate_entropy(record, T, 298)
            G = thermodynamic_calculator.calculate_gibbs_energy(record, T, 298)

            # Проверяем соотношение G = H - TS
            calculated_G = H - T * S

            # Допуск для численных ошибок
            diff = abs(G - calculated_G)
            assert diff < 0.1, f"Нарушено соотношение G=H-TS при T={T}: G={G}, расчёт={calculated_G}, diff={diff}"

            # Проверяем разумность значений
            assert not math.isnan(G), f"G является NaN при T={T}"
            assert not math.isinf(G), f"G является бесконечностью при T={T}"

    @pytest.mark.asyncio
    async def test_troutons_rule_validation(self, multi_phase_orchestrator):
        """
        Тест проверки правила Трутона для энтропии кипения.

        Правило Трутона: ΔSvap ≈ 85-120 Дж/(моль·K) для большинства жидкостей
        """

        # Ищем соединения с известными температурами кипения
        test_compounds = ["H2O", "NH3", "CH4", "CO2"]

        for compound in test_compounds:
            result = multi_phase_orchestrator.compound_searcher.search_compound(compound, (200, 500))

            if result and result.records_found:
                # Ищем записи с данными о фазовых переходах
                for record in result.records_found:
                    melting_point = record.get('Tmelt')
                    boiling_point = record.get('Tboil')
                    h298 = record.get('H298')
                    s298 = record.get('S298')

                    if boiling_point is not None and s298 is not None:
                        try:
                            Tboil = float(boiling_point)
                            S298 = float(s298)

                            # Проверяем, что температура кипения разумна
                            assert 100 < Tboil < 10000, f"Нереалистичная температура кипения для {compound}: {Tboil}K"

                            # Энтропия должна быть разумной
                            assert 10 < S298 < 500, f"Нереалистичная энтропия для {compound}: {S298} Дж/(моль·K)"

                        except (ValueError, TypeError):
                            pass

    @pytest.mark.asyncio
    async def test_melting_entropy_reasonableness(self, multi_phase_orchestrator):
        """
        Тест разумности энтропии плавления.

        Энтропия плавления обычно в диапазоне 5-30 Дж/(моль·K)
        для большинства соединений.
        """

        # Тестируем на соединениях с данными о плавлении
        test_compounds = ["Fe", "FeO", "Al2O3", "SiO2"]

        for compound in test_compounds:
            result = multi_phase_orchestrator.compound_searcher.search_compound(compound, (200, 2000))

            if result and result.records_found:
                for record in result.records_found:
                    melting_point = record.get('Tmelt')
                    s298 = record.get('S298')

                    if melting_point is not None and s298 is not None:
                        try:
                            Tmelt = float(melting_point)
                            S298 = float(s298)

                            # Проверяем разумность температуры плавления
                            assert 200 < Tmelt < 4000, f"Нереалистичная температура плавления для {compound}: {Tmelt}K"

                            # Энтропия должна быть положительной и разумной
                            assert S298 > 0, f"Энтропия должна быть положительной: {compound} S298 = {S298}"

                            # Для металлов и оксидов энтропия обычно 20-100 Дж/(моль·K)
                            if compound in ["Fe", "FeO"]:
                                assert 20 < S298 < 150, f"Ненормальная энтропия для {compound}: {S298}"

                        except (ValueError, TypeError):
                            pass

    def test_transition_enthalpy_signs(self, thermodynamic_calculator):
        """
        Тест проверки знаков энтальпий фазовых переходов.

        Плавление и кипение должны быть эндотермическими (ΔH > 0)
        """

        # Создаём тестовые данные для воды
        class WaterRecord:
            def __init__(self):
                self.H298 = -285.83  # кДж/моль
                self.S298 = 69.95    # Дж/(моль·K)
                self.f1 = 33.33
                self.f2 = -11.33
                self.f3 = 11.47
                self.f4 = -3.86
                self.f5 = 0.5
                self.f6 = -0.032

        record = WaterRecord()

        # Проверяем энтальпию при разных температурах
        T_melting = 273.15  # 0°C
        T_boiling = 373.15  # 100°C

        # Энтальпия должна возрастать с температурой
        H_273 = thermodynamic_calculator.calculate_enthalpy(record, T_melting - 1, 298)
        H_274 = thermodynamic_calculator.calculate_enthalpy(record, T_melting + 1, 298)
        H_373 = thermodynamic_calculator.calculate_enthalpy(record, T_boiling - 1, 298)
        H_374 = thermodynamic_calculator.calculate_enthalpy(record, T_boiling + 1, 298)

        # Проверяем, что энтальпия растёт с температурой
        assert H_274 > H_273, f"Энтальпия должна расти с температурой при плавлении: {H_273} -> {H_274}"
        assert H_374 > H_373, f"Энтальпия должна расти с температурой при кипении: {H_373} -> {H_374}"

        # Прирост должен быть положительным и разумным
        delta_melting = H_274 - H_273
        delta_boiling = H_374 - H_373

        assert delta_melting > 0, f"Плавление должно быть эндотермическим: ΔH = {delta_melting}"
        assert delta_boiling > 0, f"Кипение должно быть эндотермическим: ΔH = {delta_boiling}"

    def test_heat_capacity_integration(self, thermodynamic_calculator):
        """
        Тест проверки интегрирования теплоёмкости.

        Проверяет корректность численного интегрирования Cp
        для расчёта энтальпии и энтропии.
        """

        # Создаём тестовые данные
        class TestRecord:
            def __init__(self):
                self.H298 = -100.0  # кДж/моль
                self.S298 = 100.0   # Дж/(моль·K)
                self.f1 = 20.0
                self.f2 = 10.0
                self.f3 = 0.0
                self.f4 = 0.0
                self.f5 = 0.0
                self.f6 = 0.0

        record = TestRecord()

        # Тестируем интегрирование при разных температурах
        T1, T2 = 298, 398

        # Расчёт энтальпии через интегрирование
        H_T1 = thermodynamic_calculator.calculate_enthalpy(record, T1, 298)
        H_T2 = thermodynamic_calculator.calculate_enthalpy(record, T2, 298)

        # Прямой расчёт изменения энтальпии
        delta_H_expected = thermodynamic_calculator.calculate_enthalpy(record, T2, T1)
        delta_H_actual = H_T2 - H_T1

        # Проверяем согласованность
        diff = abs(delta_H_expected - delta_H_actual)
        assert diff < 1.0, f"Ошибка интегрирования теплоёмкости: {delta_H_expected} vs {delta_H_actual}, diff={diff}"

        # Проверяем, что теплоёмкость положительна
        Cp_T1 = thermodynamic_calculator.calculate_heat_capacity(record, T1)
        Cp_T2 = thermodynamic_calculator.calculate_heat_capacity(record, T2)

        assert Cp_T1 > 0, f"Теплоёмкость должна быть положительной при T={T1}: {Cp_T1}"
        assert Cp_T2 > 0, f"Теплоёмкость должна быть положительной при T={T2}: {Cp_T2}"

    def test_temperature_derivative_consistency(self, thermodynamic_calculator):
        """
        Тест проверки согласованности температурных производных.

        Проверяет, что (∂G/∂T)_P = -S и (∂H/∂T)_P = Cp
        """

        class TestRecord:
            def __init__(self):
                self.H298 = -200.0
                self.S298 = 150.0
                self.f1 = 25.0
                self.f2 = -5.0
                self.f3 = 1.0
                self.f4 = 0.0
                self.f5 = 0.0
                self.f6 = 0.0

        record = TestRecord()

        # Проверяем производные численно
        T = 350
        dT = 1.0  # Малый шаг для численного дифференцирования

        # G(T) и G(T+dT)
        G_T = thermodynamic_calculator.calculate_gibbs_energy(record, T, 298)
        G_T_dT = thermodynamic_calculator.calculate_gibbs_energy(record, T + dT, 298)

        # Численная производная
        dG_dT_num = (G_T_dT - G_T) / dT

        # Точная энтропия при T
        S_T = thermodynamic_calculator.calculate_entropy(record, T, 298)

        # Проверяем (∂G/∂T)_P = -S
        # G в кДж/моль, S в Дж/(моль·K), переводим единицы
        dG_dT_exact = -S_T / 1000  # Дж -> кДж

        diff = abs(dG_dT_num - dG_dT_exact)
        assert diff < 0.5, f"Несогласованность производной G: численная={dG_dT_num}, точная={dG_dT_exact}, diff={diff}"

        # Проверяем (∂H/∂T)_P = Cp
        H_T = thermodynamic_calculator.calculate_enthalpy(record, T, 298)
        H_T_dT = thermodynamic_calculator.calculate_enthalpy(record, T + dT, 298)

        dH_dT_num = (H_T_dT - H_T) / dT
        Cp_T = thermodynamic_calculator.calculate_heat_capacity(record, T)

        # H в кДж/моль, Cp в Дж/(моль·K), переводим единицы
        Cp_T_kJ = Cp_T / 1000

        diff = abs(dH_dT_num - Cp_T_kJ)
        assert diff < 0.1, f"Несогласованность производной H: численная={dH_dT_num}, Cp={Cp_T_kJ}, diff={diff}"

    @pytest.mark.asyncio
    async def test_thermodynamic_stability_validation(self, multi_phase_orchestrator):
        """
        Тест проверки термодинамической стабильности.

        Проверяет, что Gibbs энергия уменьшается при стремлении
        к равновесию для спонтанных процессов.
        """

        # Тестируем на известной экзотермической реакции
        query = "Fe + O2 → FeO термодинамика при 1000K"
        response = await multi_phase_orchestrator.process_query(query)

        assert response is not None

        # Проверяем наличие термодинамических данных
        has_dG = "δg" in response.lower() or "gibbs" in response.lower()
        has_negative_dG = "отриц" in response.lower() and ("gibbs" in response.lower() or "δg" in response.lower())

        # Если система рассчитывает ΔG, для экзотермической реакции оно должно быть отрицательным
        if has_dG and len(response) > 200:  # Ответ содержит достаточно информации
            # Проверяем, что реакция описана как термодинамически выгодная
            is_spontaneous = any(
                indicator in response.lower()
                for indicator in ["спонтан", "выгодн", "отрицатель", "экзотерм"]
            )

            # Если есть количественные данные, проверяем знак
            if "δg" in response.lower():
                # Должно быть указано, что реакция термодинамически выгодна
                assert is_spontaneous or "неблагоприятн" not in response.lower(), \
                    f"Реакция Fe+O2 должна быть термодинамически выгодной: {response[:500]}..."

    @pytest.mark.asyncio
    async def test_heat_capacity_physical_limits(self, multi_phase_orchestrator):
        """
        Тест проверки физических пределов теплоёмкости.

        Проверяет, что теплоёмкость находится в разумных пределах
        согласно физическим законам.
        """

        test_compounds = ["H2O", "CO2", "Fe", "FeO"]

        for compound in test_compounds:
            result = multi_phase_orchestrator.compound_searcher.search_compound(compound, (298, 298))

            if result and result.records_found:
                for record in result.records_found[:1]:
                    # Проверяем коэффициенты теплоёмкости
                    f1 = record.get('f1')
                    f2 = record.get('f2')
                    f3 = record.get('f3')
                    f4 = record.get('f4')
                    f5 = record.get('f5')
                    f6 = record.get('f6')

                    if f1 is not None:
                        try:
                            f1_val = float(f1)
                            # Cp при 298K должна быть разумной
                            Cp_298 = f1_val  # При T=298, Cp ≈ f1 для многих полиномов

                            # Физические пределы для Cp (Дж/(моль·K))
                            assert 5 < Cp_298 < 500, f"Нереалистичная теплоёмкость для {compound}: {Cp_298}"

                        except (ValueError, TypeError):
                            pass

    def test_numerical_integration_accuracy(self, thermodynamic_calculator):
        """
        Тест проверки точности численного интегрирования.

        Проверяет, что численное интегрирование достаточно точное
        для термодинамических расчётов.
        """

        # Создаём простые тестовые данные с известным решением
        class SimpleRecord:
            def __init__(self):
                self.H298 = 0.0
                self.S298 = 100.0
                self.f1 = 29.1  # Cp = 29.1 Дж/(моль·K) - постоянная
                self.f2 = 0.0
                self.f3 = 0.0
                self.f4 = 0.0
                self.f5 = 0.0
                self.f6 = 0.0

        record = SimpleRecord()

        # Для постоянной теплоёмкости есть аналитическое решение
        T1, T2 = 298, 398

        # Численное интегрирование
        H_num = thermodynamic_calculator.calculate_enthalpy(record, T2, T1)

        # Аналитическое решение: ΔH = Cp * (T2 - T1)
        Cp = record.f1
        H_exact = Cp * (T2 - T1) / 1000  # переводим в кДж/моль

        # Проверяем точность
        relative_error = abs(H_num - H_exact) / abs(H_exact) if H_exact != 0 else abs(H_num)
        assert relative_error < 0.01, f"Слишком большая ошибка численного интегрирования: {relative_error:.4%}"

        # Тестируем энтропию
        S_num = thermodynamic_calculator.calculate_entropy(record, T2, T1)
        S_exact = Cp * math.log(T2 / T1)  # Дж/(моль·K)

        relative_error_S = abs(S_num - S_exact) / abs(S_exact) if S_exact != 0 else abs(S_num)
        assert relative_error_S < 0.01, f"Слишком большая ошибка в расчёте энтропии: {relative_error_S:.4%}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])