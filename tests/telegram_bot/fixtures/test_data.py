"""
Тестовые данные для термодинамических расчётов
"""

# Тестовые химические соединения
TEST_COMPOUNDS = {
    "h2o": {
        "formula": "H2O",
        "name": "вода",
        "phase": "l",
        "H298": -285.83,
        "S298": 69.91,
        "Cp": 75.29,
        "Tmin": 273.15,
        "Tmax": 373.15,
        "Tmelt": 273.15,
        "Tboil": 373.15
    },
    "co2": {
        "formula": "CO2",
        "name": "углекислый газ",
        "phase": "g",
        "H298": -393.51,
        "S298": 213.74,
        "Cp": 44.01,
        "Tmin": 194.65,
        "Tmax": 304.13,
        "Tmelt": None,
        "Tboil": None
    },
    "h2": {
        "formula": "H2",
        "name": "водород",
        "phase": "g",
        "H298": 0.0,
        "S298": 130.68,
        "Cp": 28.84,
        "Tmin": 13.8,
        "Tmax": 1000.0,
        "Tmelt": 13.8,
        "Tboil": 20.27
    },
    "o2": {
        "formula": "O2",
        "name": "кислород",
        "phase": "g",
        "H298": 0.0,
        "S298": 205.15,
        "Cp": 29.38,
        "Tmin": 54.36,
        "Tmax": 1000.0,
        "Tmelt": 54.36,
        "Tboil": 90.20
    },
    "ch4": {
        "formula": "CH4",
        "name": "метан",
        "phase": "g",
        "H298": -74.87,
        "S298": 186.25,
        "Cp": 35.31,
        "Tmin": 90.67,
        "Tmax": 1000.0,
        "Tmelt": 90.67,
        "Tboil": 111.67
    }
}

# Тестовые реакции
TEST_REACTIONS = {
    "h2_combustion": {
        "equation": "2 H2 + O2 → 2 H2O",
        "reactants": ["H2", "O2"],
        "products": ["H2O"],
        "coefficients": {"H2": 2, "O2": 1, "H2O": 2},
        "ΔH": -571.66,
        "ΔS": -326.7,
        "ΔG": -474.24,
        "K": 2.1e+83
    },
    "methane_combustion": {
        "equation": "CH4 + 2 O2 → CO2 + 2 H2O",
        "reactants": ["CH4", "O2"],
        "products": ["CO2", "H2O"],
        "coefficients": {"CH4": 1, "O2": 2, "CO2": 1, "H2O": 2},
        "ΔH": -890.36,
        "ΔS": -242.7,
        "ΔG": -818.46,
        "K": 1.2e+144
    }
}

# Тестовые запросы пользователей
TEST_QUERIES = [
    "H2O properties at 298K",
    "CO2 properties from 200K to 400K",
    "2 H2 + O2 → 2 H2O reaction thermodynamics",
    "CH4 combustion enthalpy",
    "water boiling point",
    "carbon dioxide critical temperature",
    "thermodynamic properties of oxygen at 300K",
    "equilibrium constant for H2 + O2 → H2O",
    "enthalpy of formation methane",
    "entropy of water vapor"
]

# Ожидаемые форматы ответов
EXPECTED_RESPONSES = {
    "short_response": "ΔH = -285.83 kJ/mol",
    "medium_response": """Термодинамические свойства H2O:
ΔH° = -285.83 кДж/моль
S° = 69.91 Дж/(моль·К)
Cp = 75.29 Дж/(моль·К)""",
    "long_response": """Реакция: 2 H2 + O2 → 2 H2O

**Термодинамические параметры при 298.15 K:**
ΔH° = -571.66 кДж
ΔS° = -326.7 Дж/К
ΔG° = -474.24 кДж

**Таблица температур:**

| T (K) | ΔH (кДж) | ΔS (Дж/К) | ΔG (кДж) | K |
|-------|----------|-----------|----------|---|
| 298   | -571.66  | -326.7    | -474.24  | 2.1e+83 |
| 400   | -575.43  | -311.2    | -450.95  | 4.3e+58 |
| 600   | -583.02  | -289.1    | -410.56  | 2.1e+35 |
| 800   | -590.61  | -272.1    | -372.93  | 3.7e+19 |
| 1000  | -598.20  | -258.1    | -340.10  | 1.2e+17 |"""
}

# Параметры для performance тестов
PERFORMANCE_TEST_PARAMS = {
    "concurrent_users": 10,
    "requests_per_user": 3,
    "max_response_time": 30.0,
    "avg_response_time": 10.0,
    "memory_limit_mb": 100,
    "file_creation_count": 50,
    "file_creation_time_limit": 5.0
}

# Температурные диапазоны для тестов
TEMPERATURE_RANGES = {
    "cryogenic": (13.8, 100),
    "low_temp": (100, 273.15),
    "ambient": (273.15, 373.15),
    "high_temp": (373.15, 1000),
    "very_high_temp": (1000, 5000)
}

# Фазовые состояния
PHASES = {
    "s": "твёрдая",
    "l": "жидкая",
    "g": "газ",
    "aq": "раствор"
}

# Юнитицы измерения
UNITS = {
    "enthalpy": "кДж/моль",
    "entropy": "Дж/(моль·К)",
    "heat_capacity": "Дж/(моль·К)",
    "gibbs_energy": "кДж/моль",
    "temperature": "K",
    "pressure": "атм",
    "equilibrium_constant": "безразмерная"
}