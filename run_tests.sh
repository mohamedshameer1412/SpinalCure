#!/bin/bash
# SpinalCure Test Suite Runner
# Convenient script for running different test configurations

set -e

echo "SpinalCure Test Suite"
echo "===================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Parse command line arguments
if [ $# -eq 0 ]; then
    echo "Usage: ./run_tests.sh [command]"
    echo ""
    echo "Commands:"
    echo "  all              - Run all tests"
    echo "  unit             - Run unit tests only (fast)"
    echo "  integration      - Run integration tests only"
    echo "  otp              - Run OTP security tests"
    echo "  security         - Run all security tests"
    echo "  coverage         - Run with coverage report"
    echo "  watch            - Run tests and watch for changes"
    echo "  models           - Test models only"
    echo "  validators       - Test validators only"
    echo "  permissions      - Test permissions only"
    echo "  clean            - Clean test artifacts"
    exit 1
fi

case "$1" in
    all)
        echo -e "${YELLOW}Running all tests...${NC}"
        pytest tests/ -v --tb=short
        ;;
    unit)
        echo -e "${YELLOW}Running unit tests (fast)...${NC}"
        pytest tests/unit/ -v --tb=short
        ;;
    integration)
        echo -e "${YELLOW}Running integration tests...${NC}"
        pytest tests/integration/ -v --tb=short
        ;;
    otp)
        echo -e "${YELLOW}Running OTP security tests...${NC}"
        pytest tests/unit/test_otp.py -v --tb=short -m otp
        ;;
    security)
        echo -e "${YELLOW}Running security tests...${NC}"
        pytest tests/ -v --tb=short -m security
        ;;
    coverage)
        echo -e "${YELLOW}Running tests with coverage...${NC}"
        pytest tests/ --cov=. --cov-report=html --cov-report=term-missing -v
        echo -e "${GREEN}Coverage report generated in htmlcov/index.html${NC}"
        ;;
    watch)
        echo -e "${YELLOW}Running tests in watch mode...${NC}"
        pytest-watch tests/ -- -v --tb=short
        ;;
    models)
        echo -e "${YELLOW}Testing models...${NC}"
        pytest tests/unit/test_models.py -v --tb=short
        ;;
    validators)
        echo -e "${YELLOW}Testing validators...${NC}"
        pytest tests/unit/test_validators.py -v --tb=short
        ;;
    permissions)
        echo -e "${YELLOW}Testing permissions...${NC}"
        pytest tests/unit/test_permissions.py -v --tb=short
        ;;
    clean)
        echo -e "${YELLOW}Cleaning test artifacts...${NC}"
        rm -rf .pytest_cache/
        rm -rf htmlcov/
        rm -rf .coverage
        find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
        echo -e "${GREEN}Cleaned!${NC}"
        ;;
    *)
        echo -e "${RED}Unknown command: $1${NC}"
        exit 1
        ;;
esac
