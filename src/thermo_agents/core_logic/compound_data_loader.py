"""
Compound data loader with three-stage search strategy.

This module implements the compound data loading logic from calc_example.ipynb
with YAML cache priority and two-stage database fallback search.
"""

import logging
import pandas as pd
from typing import Optional, List, Dict, Any

from ..search.database_connector import DatabaseConnector
from ..storage.static_data_manager import StaticDataManager
from ..models.static_data import YAMLCompoundData, YAMLPhaseRecord


class CompoundDataLoader:
    """
    Загрузчик данных веществ с YAML-кэшем и двухстадийной стратегией поиска в БД.
    """

    def __init__(
        self,
        db_connector: DatabaseConnector,
        static_data_manager: StaticDataManager,
        logger: logging.Logger
    ):
        self.db_connector = db_connector
        self.static_manager = static_data_manager
        self.logger = logger

    def get_raw_compound_data(
        self,
        formula: str,
        compound_names: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """
        Трехстадийный поиск вещества (YAML → БД формула+имя → БД только формула).

        СТАДИЯ 0 (приоритет): Проверка YAML-кэша для распространенных веществ
        СТАДИЯ 1: Поиск в БД по формуле + первое имя (строгое соответствие)
        СТАДИЯ 2 (fallback): Поиск в БД только по формуле

        Args:
            formula: Химическая формула (например, "SO2", "H2O")
            compound_names: Список имен из LLM response (опционально)

        Returns:
            DataFrame со всеми найденными записями, отсортированными по:
            - ReliabilityClass (1 > 2 > 3 > 0 > 4 > 5)
            - Tmax - Tmin (больший диапазон лучше)
            - Длина формулы (короче лучше)
            - Фаза (g > l > s > aq)

        Логирование:
            - ⚡ {formula}: найдено в YAML-кэше ({N} фаз)
            - ✓ {formula} (стадия 1: формула + '{first_name}'): найдено N записей
            - ⚠ {formula}: стадия 1 не дала результатов, переход к стадии 2
            - ✓ {formula} (стадия 2: только формула): найдено N записей
            - ⚠ {formula}: не найдено записей (все стадии)
        """
        # Стадия 0: YAML-кэш (для H2O, CO2, O2, NH3, Cl2, HCl, NaCl, FeO, C, CO)
        if self.static_manager.is_available(formula):
            self.logger.info(f"⚡ {formula}: найдено в YAML-кэше")
            yaml_data = self.static_manager.load_compound(formula)
            return self._convert_yaml_to_dataframe(yaml_data)

        # Стадия 1: БД с формулой + именем
        if compound_names and len(compound_names) > 0:
            first_name = compound_names[0]
            df = self._search_db_with_name(formula, first_name)
            if not df.empty:
                self.logger.info(
                    f"✓ {formula} (стадия 1: формула + '{first_name}'): "
                    f"найдено {len(df)} записей"
                )
                return df
            else:
                self.logger.info(f"⚠ {formula}: стадия 1 не дала результатов, переход к стадии 2")

        # Стадия 2: БД только формула
        df = self._search_db_formula_only(formula)
        if not df.empty:
            self.logger.info(f"✓ {formula} (стадия 2: только формула): найдено {len(df)} записей")
        else:
            self.logger.warning(f"⚠ {formula}: не найдено записей (все стадии)")

        return df

    def _convert_yaml_to_dataframe(self, yaml_data: YAMLCompoundData) -> pd.DataFrame:
        """
        Конвертирует YAML данные в DataFrame с той же структурой, что и БД.
        """
        rows = []
        for phase_record in yaml_data.phases:
            row = {
                'Formula': yaml_data.formula,
                'FirstName': phase_record.first_name or '',
                'SecondName': '',
                'Phase': phase_record.phase,
                'Tmin': phase_record.tmin,
                'Tmax': phase_record.tmax,
                'H298': phase_record.h298 / 1000,  # Convert J to kJ
                'S298': phase_record.s298,
                'f1': phase_record.f1,
                'f2': phase_record.f2,
                'f3': phase_record.f3,
                'f4': phase_record.f4,
                'f5': phase_record.f5,
                'f6': phase_record.f6,
                'MeltingPoint': phase_record.tmelt if phase_record.tmelt != 0 else 0,
                'BoilingPoint': phase_record.tboil if phase_record.tboil != 0 else 0,
                'ReliabilityClass': phase_record.reliability_class,
                'MolecularWeight': phase_record.molecular_weight or 0,
                'rowid': phase_record.db_rowid or -1
            }
            rows.append(row)

        df = pd.DataFrame(rows)
        return self._sort_dataframe(df)

    def _search_db_with_name(self, formula: str, name: str) -> pd.DataFrame:
        """
        Стадия 1: Поиск в БД по формуле + имени.
        """
        query = f"""
        SELECT * FROM compounds
        WHERE (
            (TRIM(Formula) = '{formula}' OR Formula LIKE '{formula}(%')
            AND (TRIM(FirstName) = '{name}' OR TRIM(SecondName) = '{name}')
        )
        AND (Formula NOT LIKE '%+%' AND Formula NOT LIKE '%-%')
        ORDER BY
            CASE ReliabilityClass
                WHEN 1 THEN 0 WHEN 2 THEN 1 WHEN 3 THEN 2
                WHEN 0 THEN 3 WHEN 4 THEN 4 WHEN 5 THEN 5 ELSE 6
            END,
            (Tmax - Tmin) DESC,
            LENGTH(TRIM(Formula)) ASC,
            CASE Phase
                WHEN 'g' THEN 0 WHEN 'l' THEN 1
                WHEN 's' THEN 2 WHEN 'aq' THEN 3 ELSE 4
            END,
            rowid ASC
        """

        self.db_connector.connect()
        results = self.db_connector.execute_query(query)

        if not results:
            return pd.DataFrame()

        df = pd.DataFrame(results)
        return self._sort_dataframe(df)

    def _search_db_formula_only(self, formula: str) -> pd.DataFrame:
        """
        Стадия 2: Поиск в БД только по формуле.
        """
        query = f"""
        SELECT * FROM compounds
        WHERE (TRIM(Formula) = '{formula}' OR Formula LIKE '{formula}(%')
        AND (Formula NOT LIKE '%+%' AND Formula NOT LIKE '%-%')
        ORDER BY
            CASE ReliabilityClass
                WHEN 1 THEN 0 WHEN 2 THEN 1 WHEN 3 THEN 2
                WHEN 0 THEN 3 WHEN 4 THEN 4 WHEN 5 THEN 5 ELSE 6
            END,
            (Tmax - Tmin) DESC,
            LENGTH(TRIM(Formula)) ASC,
            CASE Phase
                WHEN 'g' THEN 0 WHEN 'l' THEN 1
                WHEN 's' THEN 2 WHEN 'aq' THEN 3 ELSE 4
            END,
            rowid ASC
        """

        self.db_connector.connect()
        results = self.db_connector.execute_query(query)

        if not results:
            return pd.DataFrame()

        df = pd.DataFrame(results)
        return self._sort_dataframe(df)

    def _sort_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Сортирует DataFrame по приоритетам (если еще не отсортирован).
        """
        if df.empty:
            return df

        # Если уже есть колонка приоритета, используем её
        if '_priority' in df.columns:
            return df.sort_values('_priority')

        # Иначе вычисляем приоритет
        df = df.copy()

        # Приоритет ReliabilityClass
        reliability_order = {1: 0, 2: 1, 3: 2, 0: 3, 4: 4, 5: 5}
        df['_reliability_score'] = df['ReliabilityClass'].map(reliability_order).fillna(6)

        # Приоритет Phase
        phase_order = {'g': 0, 'l': 1, 's': 2, 'aq': 3}
        df['_phase_score'] = df['Phase'].map(phase_order).fillna(4)

        # Вычисляем общий приоритет
        df['_priority'] = (
            df['_reliability_score'].astype(str) + '_' +
            (-(df['Tmax'] - df['Tmin'])).astype(str) + '_' +
            df['Formula'].str.len().astype(str) + '_' +
            df['_phase_score'].astype(str) + '_' +
            df.index.astype(str)
        )

        df_sorted = df.sort_values('_priority').drop(columns=['_reliability_score', '_phase_score', '_priority'])

        return df_sorted.reset_index(drop=True)

    def get_raw_compound_data_with_metadata(
        self,
        formula: str,
        compound_names: Optional[List[str]] = None
    ) -> tuple[pd.DataFrame, bool, Optional[int]]:
        """
        Трехстадийный поиск вещества с возвратом метаданных об источнике.

        Возвращает:
            - DataFrame с найденными записями
            - is_yaml_cache: bool (истинно, если данные из YAML-кэша)
            - search_stage: Optional[int] (1 или 2 для поиска в БД, None для YAML)

        Args:
            formula: Химическая формула (например, "SO2", "H2O")
            compound_names: Список имен из LLM response (опционально)

        Returns:
            (df, is_yaml_cache, search_stage)
        """
        # Стадия 0: YAML-кэш (для H2O, CO2, O2, NH3, Cl2, HCl, NaCl, FeO, C, CO)
        if self.static_manager.is_available(formula):
            self.logger.info(f"⚡ {formula}: найдено в YAML-кэше")
            yaml_data = self.static_manager.load_compound(formula)
            df = self._convert_yaml_to_dataframe(yaml_data)
            return df, True, None

        # Стадия 1: БД с формулой + именем
        if compound_names and len(compound_names) > 0:
            first_name = compound_names[0]
            df = self._search_db_with_name(formula, first_name)
            if not df.empty:
                self.logger.info(
                    f"✓ {formula} (стадия 1: формула + '{first_name}'): "
                    f"найдено {len(df)} записей"
                )
                return df, False, 1
            else:
                self.logger.info(f"⚠ {formula}: стадия 1 не дала результатов, переход к стадии 2")

        # Стадия 2: БД только формула
        df = self._search_db_formula_only(formula)
        if not df.empty:
            self.logger.info(f"✓ {formula} (стадия 2: только формула): найдено {len(df)} записей")
            return df, False, 2
        else:
            self.logger.warning(f"⚠ {formula}: не найдено записей (все стадии)")

        return df, False, None