# SpinalCure Testing Guide

## Overview

This document provides comprehensive testing guidance for the SpinalCure application. The test suite ensures code quality, security, and reliability through unit tests, integration tests, and end-to-end workflows.

## Test Structure

```
tests/
├── conftest.py                 # Pytest configuration & fixtures
├── pytest.ini                  # Pytest settings
├── unit/                       # Unit tests
│   ├── test_otp.py            # OTP authentication tests
│   ├── test_validators.py      # Input validation tests
│   ├── test_permissions.py     # RBAC permission tests
│   └── test_models.py          # Model validation tests
├── integration/                # Integration tests
│   ├── test_api_flows.py       # API workflow tests
│   ├── test_patients.py        # Patient endpoint tests
│   └── test_appointments.py    # Appointment endpoint tests
└── fixtures/                   # Reusable test data fixtures
```

## Running Tests

### Run All Tests
```bash
pytest
```

### Run with Coverage Report
```bash
pytest --cov=. --cov-report=html --cov-report=term-missing
```

### Run Specific Test File
```bash
pytest tests/unit/test_otp.py
```

### Run Specific Test Class
```bash
pytest tests/unit/test_otp.py::TestOTPTokenGeneration
```

### Run Specific Test Method
```bash
pytest tests/unit/test_otp.py::TestOTPTokenGeneration::test_generate_otp_token_creates_token
```

### Run Tests in Parallel (Faster)
```bash
pytest -n auto
```

### Run Only Unit Tests (Fast)
```bash
pytest -m unit
```

### Run Only Integration Tests
```bash
pytest -m integration
```

### Run Security Tests
```bash
pytest -m security
```

### Run OTP Tests
```bash
pytest -m otp
```

### Stop on First Failure
```bash
pytest -x
```

### Show Print Output
```bash
pytest -s
```

### Verbose Mode
```bash
pytest -v
```

## Test Categories

### Unit Tests

**Files:** `tests/unit/`

Unit tests verify individual components without external dependencies:

#### OTP Tests (`test_otp.py`)
- **TestOTPTokenGeneration**: OTP generation and security
  - `test_generate_otp_token_creates_token` - Verify OTP creation
  - `test_otp_token_has_valid_expiry` - Check 10-minute expiry
  - `test_otp_secret_is_generated` - Verify secret generation
  - `test_previous_otp_invalidated_on_new_request` - Previous OTP invalidation

- **TestOTPRateLimiting**: Rate limiting & DDoS prevention
  - `test_otp_request_rate_limiting_per_hour` - Max 3 requests/hour
  - `test_daily_otp_request_limit` - Max 5 requests/day

- **TestOTPVerification**: OTP verification workflow
  - `test_verify_otp_with_correct_code` - Successful verification
  - `test_verify_otp_with_incorrect_code` - Failed verification
  - `test_brute_force_protection_5_attempts` - Max 5 failed attempts
  - `test_otp_expires_after_10_minutes` - Expiry validation
  - `test_otp_marked_as_used_after_verification` - Usage tracking

- **TestOTPCleanup**: Token cleanup & maintenance
  - `test_cleanup_expired_tokens` - Remove expired tokens
  - `test_cleanup_does_not_remove_valid_tokens` - Preserve valid tokens

#### Validator Tests (`test_validators.py`)
- **TestPhoneNumberValidator**: Phone format validation
- **TestDateValidators**: Date past/future validation
- **TestTimeRangeValidator**: Time range validation
- **TestAmountValidators**: Financial amount validation
- **TestGSTINValidator**: Indian GST validation
- **TestIFSCValidator**: Bank IFSC code validation
- **TestUPIValidator**: UPI ID validation
- **TestEmailValidator**: Email format validation

#### Permission Tests (`test_permissions.py`)
- **TestIsSuperAdmin**: Superuser permission
- **TestIsDoctor**: Doctor role permission
- **TestIsReceptionist**: Receptionist role permission
- **TestIsOwnerOrAdmin**: Ownership/admin permission
- **TestIsPatientOwnerOrDoctor**: Patient/doctor permission
- **TestIsClinicAdmin**: Clinic admin permission

#### Model Tests (`test_models.py`)
- **TestClinicProfileModel**: Clinic profile validation
- **TestPractitionerModel**: Doctor/practitioner validation
- **TestPatientModel**: Patient data validation
- **TestAppointmentModel**: Appointment validation
- **TestDoctorAvailabilityModel**: Doctor schedule validation
- **TestPaymentModel**: Payment validation
- **TestEventModel**: Event validation
- **TestUserModel**: User model validation

### Integration Tests

**Files:** `tests/integration/`

Integration tests verify complete workflows and API interactions:

#### API Flow Tests (`test_api_flows.py`)
- **TestOTPAuthFlow**: Complete OTP authentication workflow
- **TestAppointmentFlow**: Appointment booking workflow
- **TestPaymentFlow**: Payment processing workflow
- **TestPermissionIntegration**: Permission checking across endpoints
- **TestDataValidationFlow**: End-to-end validation
- **TestEmailAndNotificationFlow**: Email notifications
- **TestUserAuthFlow**: User authentication
- **TestClinicDataFlow**: Clinic data relationships
- **TestCompleteUserJourney**: Full user workflows

#### Patient Endpoint Tests (`test_patients.py`)
- **TestPatientViewSet**: Patient CRUD operations
- **TestPatientReviewEndpoint**: Patient reviews
- **TestSessionViewSet**: Treatment session tracking

#### Appointment Endpoint Tests (`test_appointments.py`)
- **TestAppointmentViewSet**: Appointment CRUD & workflows
- **TestDoctorAvailabilityViewSet**: Doctor schedule management
- **TestAppointmentNotifications**: Appointment notifications

## Test Fixtures

### User Fixtures
```python
@pytest.fixture
def superuser():
    """Superadmin user"""
    
@pytest.fixture
def doctor_user():
    """Doctor user"""
    
@pytest.fixture
def patient_user():
    """Patient user"""
    
@pytest.fixture
def receptionist_user():
    """Receptionist user"""
```

### Authentication Fixtures
```python
@pytest.fixture
def authenticated_api_client(superuser):
    """API client with superuser authentication"""
    
@pytest.fixture
def get_jwt_token():
    """Function to generate JWT tokens"""
```

### Data Fixtures
```python
@pytest.fixture
def clinic_profile(superuser):
    """Complete clinic profile"""
    
@pytest.fixture
def practitioner(clinic_profile, doctor_user):
    """Doctor practitioner"""
    
@pytest.fixture
def patient(patient_user, clinic_profile):
    """Patient with clinic"""
    
@pytest.fixture
def appointment(patient, practitioner):
    """Scheduled appointment"""
    
@pytest.fixture
def payment(patient, clinic_profile):
    """Payment transaction"""
    
@pytest.fixture
def event(clinic_profile, superuser):
    """Scheduled event"""
```

## Writing New Tests

### Unit Test Example
```python
import pytest
from django.core.exceptions import ValidationError
from validators import validate_phone_number

@pytest.mark.unit
class TestPhoneValidator:
    """Test phone number validation."""
    
    def test_valid_phone(self):
        """Test valid phone numbers pass."""
        validate_phone_number("9876543210")  # Should not raise
    
    def test_invalid_phone(self):
        """Test invalid phone numbers fail."""
        with pytest.raises(ValidationError):
            validate_phone_number("123")
```

### Integration Test Example
```python
@pytest.mark.integration
class TestOTPFlow:
    """Test OTP authentication flow."""
    
    def test_otp_generation_and_verification(self, patient_user):
        """Test complete OTP workflow."""
        # Generate OTP
        result = OTPToken.generate_otp_token(patient_user, "email")
        assert result['success'] is True
        
        # Verify OTP
        otp_obj = OTPToken.objects.get(user=patient_user)
        verify_result = otp_obj.verify_otp(otp_obj.otp_value)
        assert verify_result['success'] is True
```

### Using Fixtures
```python
@pytest.mark.integration
def test_patient_appointments(authenticated_api_client, patient, appointment):
    """Test retrieving patient appointments."""
    url = "/api/appointments/"
    response = authenticated_api_client.get(url)
    
    assert response.status_code == 200
    assert len(response.data) >= 1
```

## Testing Best Practices

### 1. **Test Naming**
- Use descriptive names that explain what is being tested
- Follow pattern: `test_<feature>_<scenario>_<expected_result>`
- Example: `test_otp_request_rate_limiting_returns_error_on_fourth_request`

### 2. **Assertion Messages**
- Include clear messages in failed assertions
- Example: `assert payment.amount > 0, "Payment amount must be positive"`

### 3. **Test Isolation**
- Each test should be independent
- Don't rely on test execution order
- Clean up after tests (fixtures handle this)

### 4. **Mocking External Dependencies**
```python
from unittest.mock import patch
from django.test import override_settings

@patch('accounts.models.send_email')
def test_otp_email_sent(self, mock_email, patient_user):
    """Test OTP email is sent."""
    OTPToken.generate_otp_token(patient_user, "email")
    
    mock_email.assert_called_once()
```

### 5. **Database State Testing**
```python
def test_appointment_saved_to_database(self, patient, practitioner):
    """Test appointment is persisted to database."""
    appointment = Appointment.objects.create(
        patient=patient,
        doctor=practitioner,
        appointment_date="2025-03-15",
        appointment_time="09:00:00"
    )
    
    # Verify it's in the database
    assert Appointment.objects.filter(id=appointment.id).exists()
```

### 6. **Permission Testing**
```python
@pytest.mark.unit
def test_patient_cannot_access_admin_endpoints(self, patient_user):
    """Test patient is denied admin access."""
    permission = IsSuperAdmin()
    
    factory = APIRequestFactory()
    request = factory.get('/')
    request.user = patient_user
    
    assert permission.has_permission(request, None) is False
```

### 7. **Error Response Testing**
```python
def test_invalid_appointment_date_returns_validation_error(self, api_client):
    """Test validation error on invalid date."""
    response = api_client.post('/api/appointments/', {
        'appointment_date': '2020-01-01',  # Past date
        'appointment_time': '09:00:00'
    })
    
    assert response.status_code == 400
    assert 'appointment_date' in response.data
```

## Coverage Goals

- **Overall Target**: 80%+ coverage
- **Critical Components**:
  - OTP Authentication: 95%+ (security-critical)
  - Permissions: 90%+ (access control)
  - Models: 85%+ (data integrity)
  - Validators: 90%+ (input safety)
  - API Views: 80%+ (endpoints)
  - Payments: 90%+ (financial)

### Current Coverage
```bash
# To check current coverage:
pytest --cov=. --cov-report=term-missing
```

## Continuous Integration

### GitHub Actions (Example)
```yaml
name: Run Tests
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: [3.9, 3.10, 3.11]
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
        with:
          python-version: ${{ matrix.python-version }}
      - run: pip install -r requirements.txt
      - run: pytest --cov=.
```

## Debugging Tests

### Run with Detailed Output
```bash
pytest -vv -s tests/unit/test_otp.py::TestOTPTokenGeneration::test_generate_otp_token_creates_token
```

### Drop into Debugger on Failure
```bash
pytest --pdb
```

### Show Local Variables on Failure
```bash
pytest -l
```

### Run Previous Failed Tests
```bash
pytest --lf
```

## Troubleshooting

### Test Database Issues
```bash
# Reset test database
rm -rf test_db.sqlite3

# Or use Django command
python manage.py migrate --no-input
```

### Import Errors
```bash
# Ensure tests directory is a package
touch tests/__init__.py

# Check PYTHONPATH
export PYTHONPATH=$PYTHONPATH:$(pwd)
```

### Fixture Not Found
```bash
# Fixtures are in conftest.py at tests/
# Check fixture names in conftest.py
pytest --fixtures
```

### Timeout Issues
```bash
# Increase timeout for slow tests
pytest --timeout=600

# Or mark specific test as slow
@pytest.mark.slow
def test_expensive_operation():
    pass
```

## Performance Tips

1. **Use `--lf` flag** to run only recently failed tests
2. **Use `-n auto`** to run tests in parallel (requires pytest-xdist)
3. **Mark slow tests** with `@pytest.mark.slow` and skip during development
4. **Reuse fixtures** to avoid redundant setup
5. **Use `--tb=short`** to reduce output verbosity

## Security Testing Focus

### OTP Security Tests
- ✅ Rate limiting (3/hour, 5/day)
- ✅ Brute force protection (5 attempts)
- ✅ Expiry validation (10 minutes)
- ✅ Token invalidation
- ✅ DDoS prevention

### Permission Tests
- ✅ Role-based access control
- ✅ Object-level permissions
- ✅ Endpoint authorization
- ✅ Cross-user data access prevention

### Input Validation Tests
- ✅ Phone number format
- ✅ Email format
- ✅ Date ranges
- ✅ Financial amounts
- ✅ GSTIN/IFSC codes

## Maintenance

### Regular Tasks
- **Weekly**: Run full test suite with coverage
- **Per Release**: Ensure 80%+ coverage maintained
- **Monthly**: Update test fixtures with real scenarios
- **Quarterly**: Review and refactor old tests

### Growing Test Suite
- Add tests for each bug fix
- Write tests before implementing features (TDD)
- Review coverage reports regularly
- Refactor tests as code changes

## Common Issues & Solutions

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError` | Check `sys.path` and `PYTHONPATH` |
| Fixture not found | Confirm in `conftest.py` |
| Database locked | Use `--reuse-db` flag or reset |
| Slow tests | Use `pytest -n auto` for parallel |
| Import errors | Run from project root |
| Permission denied | Check file permissions |

## Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [Django Testing Guide](https://docs.djangoproject.com/en/4.2/topics/testing/)
- [DRF Testing](https://www.django-rest-framework.org/api-guide/testing/)
- [Factory Boy](https://factoryboy.readthedocs.io/)

## Contact & Support

For test-related questions or issues:
- Check test documentation in docstrings
- Review example tests in each test file
- Run `pytest --help` for CLI options
- Consult this guide's troubleshooting section

---

**Test Suite Version:** 1.0  
**Last Updated:** March 6, 2026  
**Maintainer:** QA Team
