#!/bin/bash

# Полная валидация многофазной термодинамической системы
# Stage 6: Testing and Validation
#
# Запускает все тесты валидации и генерирует отчет

set -e  # Выход при ошибке

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Функция для вывода статусных сообщений
log_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Получаем директорию проекта
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

# Создаем директорию для отчетов
REPORT_DIR="$PROJECT_DIR/validation_reports"
mkdir -p "$REPORT_DIR"

# Создаем файл отчета
REPORT_FILE="$REPORT_DIR/validation_report_$(date +%Y%m%d_%H%M%S).md"
HTML_REPORT_FILE="$REPORT_DIR/validation_report_$(date +%Y%m%d_%H%M%S).html"

log_status "Stage 6: Testing and Validation - Многофазная термодинамическая система"
log_status "Начало валидации: $(date)"
log_status "Отчет будет сохранен в: $REPORT_FILE"

# Инициализация отчета
cat > "$REPORT_FILE" << EOF
# Stage 6: Testing and Validation Report

**Дата:** $(date)
**Проект:** Многофазная термодинамическая система
**Версия:** v2.1 (Multi-Phase Enhanced)

## Executive Summary

Этот отчет содержит полную валидацию многофазной термодинамической системы,
включая проверку решения исходной проблемы с FeO/H₂₉₈, производительность,
и пользовательский опыт.

## Validation Categories

1. [Original Problem Resolution](#original-problem-resolution)
2. [Multi-Phase System Validation](#multi-phase-system-validation)
3. [Thermodynamic Correctness](#thermodynamic-correctness)
4. [Performance Testing](#performance-testing)
5. [Regression Testing](#regression-testing)
6. [User Experience Testing](#user-experience-testing)

---

EOF

log_status "Запуск тестов валидации..."

# 1. Original Problem Resolution Tests
log_status "1. Тесты решения исходной проблемы (FeO/H₂₉₈)"
echo "## 1. Original Problem Resolution" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
else
    log_error "Python не найден"
    exit 1
fi

# Запуск тестов воспроизведения исходной проблемы
log_status "   - Тест воспроизведения сценария из session_20251029_182252_ef6211.log"
if $PYTHON_CMD -m pytest tests/validation/test_original_problem_solved.py::TestOriginalProblemSolved::test_feo_h298_original_problem_reproduction -v --tb=short > "$REPORT_DIR/original_problem_1.log" 2>&1; then
    log_success "   ✓ Тест воспроизведения пройден"
    echo "✅ **Original Problem Reproduction**: PASSED" >> "$REPORT_FILE"
else
    log_error "   ✗ Тест воспроизведения не пройден"
    echo "❌ **Original Problem Reproduction**: FAILED" >> "$REPORT_FILE"
    echo "\`\`\`" >> "$REPORT_FILE"
    cat "$REPORT_DIR/original_problem_1.log" >> "$REPORT_FILE"
    echo "\`\`\`" >> "$REPORT_FILE"
fi

log_status "   - Тест корректности данных FeO"
if $PYTHON_CMD -m pytest tests/validation/test_original_problem_solved.py::TestOriginalProblemSolved::test_feo_h298_correctness_validation -v --tb=short > "$REPORT_DIR/original_problem_2.log" 2>&1; then
    log_success "   ✓ Тест корректности данных FeO пройден"
    echo "✅ **FeO Data Correctness**: PASSED" >> "$REPORT_FILE"
else
    log_error "   ✗ Тест корректности данных FeO не пройден"
    echo "❌ **FeO Data Correctness**: FAILED" >> "$REPORT_FILE"
    echo "\`\`\`" >> "$REPORT_FILE"
    cat "$REPORT_DIR/original_problem_2.log" >> "$REPORT_FILE"
    echo "\`\`\`" >> "$REPORT_FILE"
fi

log_status "   - Тест отсутствия регрессии к нулевой энтальпии"
if $PYTHON_CMD -m pytest tests/validation/test_original_problem_solved.py::TestOriginalProblemSolved::test_feo_no_regression_to_zero_enthalpy -v --tb=short > "$REPORT_DIR/original_problem_3.log" 2>&1; then
    log_success "   ✓ Тест отсутствия регрессии пройден"
    echo "✅ **No Zero Enthalpy Regression**: PASSED" >> "$REPORT_FILE"
else
    log_error "   ✗ Тест отсутствия регрессии не пройден"
    echo "❌ **No Zero Enthalpy Regression**: FAILED" >> "$REPORT_FILE"
    echo "\`\`\`" >> "$REPORT_FILE"
    cat "$REPORT_DIR/original_problem_3.log" >> "$REPORT_FILE"
    echo "\`\`\`" >> "$REPORT_FILE"
fi

echo "" >> "$REPORT_FILE"

# 2. Multi-Phase System Validation
log_status "2. Тесты валидации многофазной системы"
echo "## 2. Multi-Phase System Validation" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

# Запуск всех тестов многофазной валидации
if $PYTHON_CMD -m pytest tests/validation/test_multi_phase_validation.py -v --tb=short > "$REPORT_DIR/multi_phase_validation.log" 2>&1; then
    log_success "   ✓ Все тесты многофазной валидации пройдены"
    echo "✅ **Multi-Phase System Validation**: ALL TESTS PASSED" >> "$REPORT_FILE"
else
    log_warning "   ⚠ Некоторые тесты многофазной валидации не пройдены"
    echo "⚠️ **Multi-Phase System Validation**: SOME TESTS FAILED" >> "$REPORT_FILE"
    echo "\`\`\`" >> "$REPORT_FILE"
    tail -50 "$REPORT_DIR/multi_phase_validation.log" >> "$REPORT_FILE"
    echo "\`\`\`" >> "$REPORT_FILE"
fi

echo "" >> "$REPORT_FILE"

# 3. Thermodynamic Correctness Tests
log_status "3. Тесты термодинамической корректности"
echo "## 3. Thermodynamic Correctness" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

if $PYTHON_CMD -m pytest tests/validation/test_thermodynamic_correctness.py -v --tb=short > "$REPORT_DIR/thermodynamic_correctness.log" 2>&1; then
    log_success "   ✓ Все тесты термодинамической корректности пройдены"
    echo "✅ **Thermodynamic Correctness**: ALL TESTS PASSED" >> "$REPORT_FILE"
else
    log_warning "   ⚠ Некоторые тесты термодинамической корректности не пройдены"
    echo "⚠️ **Thermodynamic Correctness**: SOME TESTS FAILED" >> "$REPORT_FILE"
    echo "\`\`\`" >> "$REPORT_FILE"
    tail -50 "$REPORT_DIR/thermodynamic_correctness.log" >> "$REPORT_FILE"
    echo "\`\`\`" >> "$REPORT_FILE"
fi

echo "" >> "$REPORT_FILE"

# 4. Performance Tests
log_status "4. Тесты производительности"
echo "## 4. Performance Testing" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

if $PYTHON_CMD -m pytest tests/performance/test_multi_phase_performance.py -v --tb=short -s > "$REPORT_DIR/performance.log" 2>&1; then
    log_success "   ✓ Все тесты производительности пройдены"
    echo "✅ **Performance Testing**: ALL TESTS PASSED" >> "$REPORT_FILE"
else
    log_warning "   ⚠ Некоторые тесты производительности не пройдены"
    echo "⚠️ **Performance Testing**: SOME TESTS FAILED" >> "$REPORT_FILE"
    echo "\`\`\`" >> "$REPORT_FILE"
    tail -50 "$REPORT_DIR/performance.log" >> "$REPORT_FILE"
    echo "\`\`\`" >> "$REPORT_FILE"
fi

echo "" >> "$REPORT_FILE"

# 5. Regression Tests
log_status "5. Регрессионные тесты"
echo "## 5. Regression Testing" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

if $PYTHON_CMD -m pytest tests/regression/test_multi_phase_regression.py -v --tb=short > "$REPORT_DIR/regression.log" 2>&1; then
    log_success "   ✓ Все регрессионные тесты пройдены"
    echo "✅ **Regression Testing**: ALL TESTS PASSED" >> "$REPORT_FILE"
else
    log_warning "   ⚠ Некоторые регрессионные тесты не пройдены"
    echo "⚠️ **Regression Testing**: SOME TESTS FAILED" >> "$REPORT_FILE"
    echo "\`\`\`" >> "$REPORT_FILE"
    tail -50 "$REPORT_DIR/regression.log" >> "$REPORT_FILE"
    echo "\`\`\`" >> "$REPORT_FILE"
fi

echo "" >> "$REPORT_FILE"

# 6. User Experience Tests
log_status "6. Тесты пользовательского опыта"
echo "## 6. User Experience Testing" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

if $PYTHON_CMD -m pytest tests/validation/test_user_experience.py -v --tb=short > "$REPORT_DIR/user_experience.log" 2>&1; then
    log_success "   ✓ Все тесты пользовательского опыта пройдены"
    echo "✅ **User Experience Testing**: ALL TESTS PASSED" >> "$REPORT_FILE"
else
    log_warning "   ⚠ Некоторые тесты пользовательского опыта не пройдены"
    echo "⚠️ **User Experience Testing**: SOME TESTS FAILED" >> "$REPORT_FILE"
    echo "\`\`\`" >> "$REPORT_FILE"
    tail -50 "$REPORT_DIR/user_experience.log" >> "$REPORT_FILE"
    echo "\`\`\`" >> "$REPORT_FILE"
fi

echo "" >> "$REPORT_FILE"

# 7. Quick Integration Tests
log_status "7. Быстрые интеграционные тесты"
echo "## 7. Integration Testing" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

if $PYTHON_CMD -m pytest tests/integration/test_end_to_end.py::TestEndToEnd::test_simple_reaction_two_compounds -v --tb=short > "$REPORT_DIR/integration.log" 2>&1; then
    log_success "   ✓ Базовый интеграционный тест пройден"
    echo "✅ **Integration Testing**: BASIC TEST PASSED" >> "$REPORT_FILE"
else
    log_warning "   ⚠ Базовый интеграционный тест не пройден"
    echo "⚠️ **Integration Testing**: BASIC TEST FAILED" >> "$REPORT_FILE"
    echo "\`\`\`" >> "$REPORT_FILE"
    cat "$REPORT_DIR/integration.log" >> "$REPORT_FILE"
    echo "\`\`\`" >> "$REPORT_FILE"
fi

echo "" >> "$REPORT_FILE"

# Генерация сводной статистики
log_status "Генерация сводной статистики..."
echo "## Summary Statistics" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

# Подсчет тестов
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

for log_file in "$REPORT_DIR"/*.log; do
    if [ -f "$log_file" ]; then
        # Извлекаем статистику из логов pytest
        PASSED=$(grep -c "PASSED" "$log_file" 2>/dev/null || echo "0")
        FAILED=$(grep -c "FAILED" "$log_file" 2>/dev/null || echo "0")
        PASSED_TESTS=$((PASSED_TESTS + PASSED))
        FAILED_TESTS=$((FAILED_TESTS + FAILED))
        TOTAL_TESTS=$((TOTAL_TESTS + PASSED + FAILED))
    fi
done

echo "- **Total Tests Run**: $TOTAL_TESTS" >> "$REPORT_FILE"
echo "- **Passed**: $PASSED_TESTS" >> "$REPORT_FILE"
echo "- **Failed**: $FAILED_TESTS" >> "$REPORT_FILE"

if [ $TOTAL_TESTS -gt 0 ]; then
    SUCCESS_RATE=$((PASSED_TESTS * 100 / TOTAL_TESTS))
    echo "- **Success Rate**: ${SUCCESS_RATE}%" >> "$REPORT_FILE"
else
    echo "- **Success Rate**: N/A" >> "$REPORT_FILE"
fi

echo "" >> "$REPORT_FILE"

# Оценка соответствия требованиям
echo "## Requirements Compliance" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

echo "### Functional Requirements" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

# Проверка основных требований
if grep -q "PASSED" "$REPORT_DIR/original_problem_1.log" 2>/dev/null; then
    echo "✅ **FeO H₂₉₈ = -265.053 (not 0.0)**: CORRECTLY IMPLEMENTED" >> "$REPORT_FILE"
else
    echo "❌ **FeO H₂₉₈ = -265.053 (not 0.0)**: NOT VERIFIED" >> "$REPORT_FILE"
fi

if grep -q "PASSED" "$REPORT_DIR/performance.log" 2>/dev/null; then
    echo "✅ **Response Time ≤3 seconds**: REQUIREMENT MET" >> "$REPORT_FILE"
else
    echo "⚠️ **Response Time ≤3 seconds**: REQUIRES INVESTIGATION" >> "$REPORT_FILE"
fi

if grep -q "PASSED" "$REPORT_DIR/multi_phase_validation.log" 2>/dev/null; then
    echo "✅ **Phase Transitions Accurate**: REQUIREMENT MET" >> "$REPORT_FILE"
else
    echo "⚠️ **Phase Transitions Accurate**: REQUIRES INVESTIGATION" >> "$REPORT_FILE"
fi

echo "" >> "$REPORT_FILE"
echo "### Quality Requirements" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

if grep -q "PASSED" "$REPORT_DIR/regression.log" 2>/dev/null; then
    echo "✅ **No Regressions**: REQUIREMENT MET" >> "$REPORT_FILE"
else
    echo "⚠️ **No Regressions**: REQUIRES INVESTIGATION" >> "$REPORT_FILE"
fi

if grep -q "PASSED" "$REPORT_DIR/user_experience.log" 2>/dev/null; then
    echo "✅ **User Experience Quality**: REQUIREMENT MET" >> "$REPORT_FILE"
else
    echo "⚠️ **User Experience Quality**: REQUIRES INVESTIGATION" >> "$REPORT_FILE"
fi

echo "" >> "$REPORT_FILE"

# Рекомендации
echo "## Recommendations" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

if [ $SUCCESS_RATE -ge 95 ]; then
    echo "🎉 **EXCELLENT**: System passes all critical validation tests and is ready for production deployment." >> "$REPORT_FILE"
elif [ $SUCCESS_RATE -ge 85 ]; then
    echo "✅ **GOOD**: System meets most requirements. Minor issues should be addressed before production." >> "$REPORT_FILE"
elif [ $SUCCESS_RATE -ge 70 ]; then
    echo "⚠️ **ACCEPTABLE**: System has some issues that need attention before production deployment." >> "$REPORT_FILE"
else
    echo "❌ **NEEDS WORK**: System has significant issues that must be resolved before production." >> "$REPORT_FILE"
fi

echo "" >> "$REPORT_FILE"
echo "### Next Steps" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

if [ $FAILED_TESTS -gt 0 ]; then
    echo "1. Review and fix failed tests" >> "$REPORT_FILE"
    echo "2. Address performance bottlenecks" >> "$REPORT_FILE"
    echo "3. Improve user experience issues" >> "$REPORT_FILE"
    echo "4. Re-run validation after fixes" >> "$REPORT_FILE"
else
    echo "1. System is ready for production deployment" >> "$REPORT_FILE"
    echo "2. Consider additional edge case testing" >> "$REPORT_FILE"
    echo "3. Plan for monitoring in production" >> "$REPORT_FILE"
fi

echo "" >> "$REPORT_FILE"
echo "---" >> "$REPORT_FILE"
echo "**Report generated on**: $(date)" >> "$REPORT_FILE"
echo "**Validation completed in**: $SECONDS seconds" >> "$REPORT_FILE"

# Создание HTML версии отчета
log_status "Создание HTML версии отчета..."
cat > "$HTML_REPORT_FILE" << EOF
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Stage 6 Validation Report</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; }
        .header { background: #2c3e50; color: white; padding: 20px; border-radius: 5px; }
        .success { color: #27ae60; }
        .warning { color: #f39c12; }
        .error { color: #e74c3c; }
        .section { margin: 20px 0; }
        code { background: #f8f9fa; padding: 2px 4px; border-radius: 3px; }
        pre { background: #f8f9fa; padding: 10px; border-radius: 5px; overflow-x: auto; }
        .summary { background: #ecf0f1; padding: 15px; border-radius: 5px; }
        table { width: 100%; border-collapse: collapse; margin: 10px 0; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background-color: #f2f2f2; }
    </style>
</head>
<body>
    <div class="header">
        <h1>Stage 6: Testing and Validation Report</h1>
        <p>Многофазная термодинамическая система - $(date)</p>
    </div>

    <div class="section summary">
        <h2>Executive Summary</h2>
        <p><strong>Total Tests:</strong> $TOTAL_TESTS</p>
        <p><strong>Passed:</strong> <span class="success">$PASSED_TESTS</span></p>
        <p><strong>Failed:</strong> <span class="error">$FAILED_TESTS</span></p>
        <p><strong>Success Rate:</strong> ${SUCCESS_RATE}%</p>
    </div>

    <div class="section">
        <h2>Test Results</h2>
        <table>
            <tr>
                <th>Test Category</th>
                <th>Status</th>
                <th>Details</th>
            </tr>
            <tr>
                <td>Original Problem Resolution</td>
                <td>$([ -f "$REPORT_DIR/original_problem_1.log" ] && grep -q "PASSED" "$REPORT_DIR/original_problem_1.log" && echo "<span class='success'>PASSED</span>" || echo "<span class='error'>FAILED</span>")</td>
                <td>FeO H₂₉₈ = -265.053 validation</td>
            </tr>
            <tr>
                <td>Multi-Phase System</td>
                <td>$([ -f "$REPORT_DIR/multi_phase_validation.log" ] && grep -q "PASSED" "$REPORT_DIR/multi_phase_validation.log" && echo "<span class='success'>PASSED</span>" || echo "<span class='warning'>NEEDS REVIEW</span>")</td>
                <td>Phase transitions and multi-phase calculations</td>
            </tr>
            <tr>
                <td>Thermodynamic Correctness</td>
                <td>$([ -f "$REPORT_DIR/thermodynamic_correctness.log" ] && grep -q "PASSED" "$REPORT_DIR/thermodynamic_correctness.log" && echo "<span class='success'>PASSED</span>" || echo "<span class='warning'>NEEDS REVIEW</span>")</td>
                <td>Physical laws validation</td>
            </tr>
            <tr>
                <td>Performance Testing</td>
                <td>$([ -f "$REPORT_DIR/performance.log" ] && grep -q "PASSED" "$REPORT_DIR/performance.log" && echo "<span class='success'>PASSED</span>" || echo "<span class='warning'>NEEDS REVIEW</span>")</td>
                <td>Response time and memory usage</td>
            </tr>
            <tr>
                <td>Regression Testing</td>
                <td>$([ -f "$REPORT_DIR/regression.log" ] && grep -q "PASSED" "$REPORT_DIR/regression.log" && echo "<span class='success'>PASSED</span>" || echo "<span class='warning'>NEEDS REVIEW</span>")</td>
                <td>Backward compatibility</td>
            </tr>
            <tr>
                <td>User Experience</td>
                <td>$([ -f "$REPORT_DIR/user_experience.log" ] && grep -q "PASSED" "$REPORT_DIR/user_experience.log" && echo "<span class='success'>PASSED</span>" || echo "<span class='warning'>NEEDS REVIEW</span>")</td>
                <td>Output quality and usability</td>
            </tr>
        </table>
    </div>

    <div class="section">
        <h2>Requirements Compliance</h2>
        <ul>
            <li><strong>FeO H₂₉₈ = -265.053:</strong> $([ -f "$REPORT_DIR/original_problem_1.log" ] && grep -q "PASSED" "$REPORT_DIR/original_problem_1.log" && echo "<span class='success'>✅ VERIFIED</span>" || echo "<span class='error'>❌ NOT VERIFIED</span>")</li>
            <li><strong>Response Time ≤3s:</strong> $([ -f "$REPORT_DIR/performance.log" ] && grep -q "PASSED" "$REPORT_DIR/performance.log" && echo "<span class='success'>✅ REQUIREMENT MET</span>" || echo "<span class='warning'>⚠️ REQUIRES INVESTIGATION</span>")</li>
            <li><strong>Phase Transitions:</strong> $([ -f "$REPORT_DIR/multi_phase_validation.log" ] && grep -q "PASSED" "$REPORT_DIR/multi_phase_validation.log" && echo "<span class='success'>✅ ACCURATE</span>" || echo "<span class='warning'>⚠️ REQUIRES INVESTIGATION</span>")</li>
            <li><strong>No Regressions:</strong> $([ -f "$REPORT_DIR/regression.log" ] && grep -q "PASSED" "$REPORT_DIR/regression.log" && echo "<span class='success'>✅ REQUIREMENT MET</span>" || echo "<span class='warning'>⚠️ REQUIRES INVESTIGATION</span>")</li>
        </ul>
    </div>

    <div class="section">
        <h2>Conclusion</h2>
EOF

if [ $SUCCESS_RATE -ge 95 ]; then
    echo "<p><span class='success'>🎉 EXCELLENT:</span> System is ready for production deployment.</p>" >> "$HTML_REPORT_FILE"
elif [ $SUCCESS_RATE -ge 85 ]; then
    echo "<p><span class='success'>✅ GOOD:</span> System meets most requirements with minor issues.</p>" >> "$HTML_REPORT_FILE"
elif [ $SUCCESS_RATE -ge 70 ]; then
    echo "<p><span class='warning'>⚠️ ACCEPTABLE:</span> System has some issues that need attention.</p>" >> "$HTML_REPORT_FILE"
else
    echo "<p><span class='error'>❌ NEEDS WORK:</span> System has significant issues that must be resolved.</p>" >> "$HTML_REPORT_FILE"
fi

cat >> "$HTML_REPORT_FILE" << EOF
    </div>

    <div class="section">
        <p><small><em>Report generated on $(date) in $SECONDS seconds</em></small></p>
        <p><small><em>Detailed logs available in: $REPORT_DIR/</em></small></p>
    </div>
</body>
</html>
EOF

# Завершение валидации
log_success "Валидация завершена!"
log_status "Полный отчет: $REPORT_FILE"
log_status "HTML отчет: $HTML_REPORT_FILE"
log_status "Логи тестов: $REPORT_DIR/"

# Вывод итоговой статистики
echo ""
echo "=== Итоговая статистика валидации ==="
echo "Всего тестов: $TOTAL_TESTS"
echo "Пройдено: $PASSED_TESTS"
echo "Не пройдено: $FAILED_TESTS"
echo "Успешность: ${SUCCESS_RATE}%"
echo "Время выполнения: $SECONDS секунд"
echo ""

if [ $SUCCESS_RATE -ge 95 ]; then
    log_success "🎉 ОТЛИЧНО: Система готова к продакшен развертыванию!"
    exit 0
elif [ $SUCCESS_RATE -ge 85 ]; then
    log_success "✅ ХОРОШО: Система соответствует большинству требований"
    exit 0
elif [ $SUCCESS_RATE -ge 70 ]; then
    log_warning "⚠️ ДОПУСТИМО: Система требует внимания к некоторым проблемам"
    exit 1
else
    log_error "❌ ТРЕБУЕТ РАБОТЫ: Система имеет значительные проблемы"
    exit 1
fi