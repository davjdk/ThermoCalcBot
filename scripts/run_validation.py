#!/usr/bin/env python3
"""
Windows-compatible validation runner for Stage 6 Testing and Validation.

This script provides cross-platform validation testing for the multi-phase
thermodynamic system, including original problem resolution verification.
"""

import os
import sys
import subprocess
import datetime
import json
from pathlib import Path

# Colors for terminal output
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    ENDC = '\033[0m'

def log_status(message):
    print(f"{Colors.BLUE}[INFO]{Colors.ENDC} {message}")

def log_success(message):
    print(f"{Colors.GREEN}[SUCCESS]{Colors.ENDC} {message}")

def log_warning(message):
    print(f"{Colors.YELLOW}[WARNING]{Colors.ENDC} {message}")

def log_error(message):
    print(f"{Colors.RED}[ERROR]{Colors.ENDC} {message}")

def run_test_command(test_name, command, report_dir):
    """Run a test command and return results."""
    log_status(f"Running {test_name}...")

    log_file = report_dir / f"{test_name.replace(' ', '_').lower()}.log"

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=300  # 5 minutes timeout
        )

        with open(log_file, 'w', encoding='utf-8') as f:
            f.write(f"Command: {command}\n")
            f.write(f"Return code: {result.returncode}\n")
            f.write("\n=== STDOUT ===\n")
            f.write(result.stdout)
            f.write("\n=== STDERR ===\n")
            f.write(result.stderr)

        success = result.returncode == 0
        if success:
            log_success(f"   ✓ {test_name} passed")
        else:
            log_error(f"   ✗ {test_name} failed")

        return success, log_file

    except subprocess.TimeoutExpired:
        log_error(f"   ✗ {test_name} timed out")
        with open(log_file, 'w', encoding='utf-8') as f:
            f.write(f"Command: {command}\n")
            f.write("Result: TIMEOUT\n")
        return False, log_file
    except Exception as e:
        log_error(f"   ✗ {test_name} error: {e}")
        with open(log_file, 'w', encoding='utf-8') as f:
            f.write(f"Command: {command}\n")
            f.write(f"Result: ERROR - {e}\n")
        return False, log_file

def main():
    """Main validation runner."""
    project_dir = Path(__file__).parent.parent
    os.chdir(project_dir)

    # Create report directory
    report_dir = project_dir / "validation_reports"
    report_dir.mkdir(exist_ok=True)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    log_status("Stage 6: Testing and Validation - Multi-Phase Thermodynamic System")
    log_status(f"Start time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log_status(f"Reports directory: {report_dir}")

    # Test configuration
    tests = [
        {
            "name": "Original Problem Reproduction",
            "command": "python -m pytest tests/validation/test_original_problem_solved.py::TestOriginalProblemSolved::test_feo_h298_original_problem_reproduction -v --tb=short",
            "critical": True
        },
        {
            "name": "FeO Data Correctness",
            "command": "python -m pytest tests/validation/test_original_problem_solved.py::TestOriginalProblemSolved::test_feo_h298_correctness_validation -v --tb=short",
            "critical": True
        },
        {
            "name": "Multi-Phase Validation",
            "command": "python -m pytest tests/validation/test_multi_phase_validation.py -v --tb=short",
            "critical": False
        },
        {
            "name": "Thermodynamic Correctness",
            "command": "python -m pytest tests/validation/test_thermodynamic_correctness.py -v --tb=short",
            "critical": False
        },
        {
            "name": "Performance Testing",
            "command": "python -m pytest tests/performance/test_multi_phase_performance.py -v --tb=short -s",
            "critical": False
        },
        {
            "name": "Regression Testing",
            "command": "python -m pytest tests/regression/test_multi_phase_regression.py -v --tb=short",
            "critical": False
        },
        {
            "name": "User Experience Testing",
            "command": "python -m pytest tests/validation/test_user_experience.py -v --tb=short",
            "critical": False
        },
        {
            "name": "Integration Testing",
            "command": "python -m pytest tests/integration/test_end_to_end.py::TestEndToEnd::test_simple_reaction_two_compounds -v --tb=short",
            "critical": False
        }
    ]

    # Run tests
    results = []
    critical_passed = 0
    critical_total = 0

    for test in tests:
        success, log_file = run_test_command(test["name"], test["command"], report_dir)
        results.append({
            "name": test["name"],
            "success": success,
            "critical": test["critical"],
            "log_file": log_file
        })

        if test["critical"]:
            critical_total += 1
            if success:
                critical_passed += 1

    # Generate summary
    total_tests = len(results)
    passed_tests = sum(1 for r in results if r["success"])
    failed_tests = total_tests - passed_tests
    success_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0

    print("\n" + "="*60)
    print("VALIDATION SUMMARY")
    print("="*60)
    print(f"Total Tests: {total_tests}")
    print(f"Passed: {passed_tests}")
    print(f"Failed: {failed_tests}")
    print(f"Success Rate: {success_rate:.1f}%")
    print(f"Critical Tests: {critical_passed}/{critical_total}")
    print("="*60)

    # Detailed results
    print("\nDETAILED RESULTS:")
    for result in results:
        status = "✅ PASS" if result["success"] else "❌ FAIL"
        critical = " [CRITICAL]" if result["critical"] else ""
        print(f"{status} {result['name']}{critical}")

    # Generate JSON report
    json_report = {
        "timestamp": timestamp,
        "summary": {
            "total_tests": total_tests,
            "passed_tests": passed_tests,
            "failed_tests": failed_tests,
            "success_rate": success_rate,
            "critical_passed": critical_passed,
            "critical_total": critical_total
        },
        "results": [
            {
                "name": r["name"],
                "success": r["success"],
                "critical": r["critical"],
                "log_file": str(r["log_file"].relative_to(project_dir))
            }
            for r in results
        ]
    }

    json_file = report_dir / f"validation_report_{timestamp}.json"
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(json_report, f, indent=2, ensure_ascii=False)

    print(f"\nDetailed report saved to: {json_file}")

    # Final assessment
    print("\n" + "="*60)
    if critical_passed == critical_total and critical_total > 0:
        if success_rate >= 95:
            log_success("🎉 EXCELLENT: System is ready for production deployment!")
            return 0
        elif success_rate >= 85:
            log_success("✅ GOOD: System meets most requirements")
            return 0
        elif success_rate >= 70:
            log_warning("⚠️ ACCEPTABLE: System needs attention to some issues")
            return 1
        else:
            log_error("❌ NEEDS WORK: System has significant issues")
            return 2
    else:
        log_error("❌ CRITICAL TESTS FAILED: System not ready for production")
        return 2

if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        log_warning("Validation interrupted by user")
        sys.exit(130)
    except Exception as e:
        log_error(f"Validation runner error: {e}")
        sys.exit(1)