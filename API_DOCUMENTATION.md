# SpinalCure API Documentation

## Overview

SpinalCure uses **drf-spectacular** for automatic OpenAPI 3.0 schema generation and interactive API documentation. This provides comprehensive, automatically-generated documentation for all REST API endpoints.

## API Documentation Endpoints

Access interactive API documentation at these URLs:

### Swagger UI (Interactive)
```
http://localhost:8000/api/schema/swagger/
```
Modern, user-friendly interface for testing API endpoints directly in your browser.

### ReDoc (Clean, Static)
```
http://localhost:8000/api/schema/redoc/
```
Clean, reader-friendly documentation (when available).

### OpenAPI Schema (JSON)
```
http://localhost:8000/api/schema/
```
Raw OpenAPI 3.0 schema in JSON format for external tools and integrations.

---

## API Endpoints

### Authentication & Password Reset
**Base:** `/api/auth/`

#### Request OTP for Password Reset
```
POST /api/auth/request-otp/
```
Request a one-time password for password reset.

**Request Body:**
```json
{
  "email": "user@clinic.com",
  "delivery_method": "email"
}
```

**Response (200):**
```json
{
  "detail": "OTP has been sent to your email.",
  "delivery_method": "email",
  "expires_in_minutes": 10,
  "remaining_attempts": 5
}
```

**Rate Limiting:** Max 3 requests per hour per user

---

#### Verify OTP & Reset Password
```
POST /api/auth/verify-otp/
```
Verify the OTP and set a new password.

**Request Body:**
```json
{
  "email": "user@clinic.com",
  "otp": "123456",
  "delivery_method": "email",
  "new_password": "SecureNewPassword123",
  "confirm_password": "SecureNewPassword123"
}
```

**Response (200):**
```json
{
  "detail": "Password has been reset successfully.",
  "user": {
    "id": 1,
    "username": "user",
    "email": "user@clinic.com",
    "first_name": "John",
    "last_name": "Doe",
    "role": "patient"
  }
}
```

**Brute Force Protection:** Max 5 failed attempts

---

#### Get Current User Info
```
GET /api/auth/me/
```
Get information about the currently authenticated user.

**Response (200):**
```json
{
  "id": 1,
  "username": "john_doe",
  "email": "john@example.com",
  "first_name": "John",
  "last_name": "Doe",
  "role": "patient",
  "phone": "+1234567890",
  "bio": "Patient seeking spinal care"
}
```

---

### Clinic Management
**Base:** `/api/clinic/`

#### Clinic Profiles
```
GET    /api/clinic/profiles/          # List all clinics
POST   /api/clinic/profiles/          # Create clinic (admin only)
GET    /api/clinic/profiles/{id}/     # Retrieve specific clinic
PUT    /api/clinic/profiles/{id}/     # Update clinic
DELETE /api/clinic/profiles/{id}/     # Delete clinic
```

#### Practitioners
```
GET    /api/clinic/practitioners/          # List practitioners
POST   /api/clinic/practitioners/          # Add practitioner
GET    /api/clinic/practitioners/{id}/     # Practitioner details
PUT    /api/clinic/practitioners/{id}/     # Update practitioner
DELETE /api/clinic/practitioners/{id}/     # Delete practitioner
```

---

### Patient Management
**Base:** `/api/`

#### Patients
```
GET    /api/patients/          # List patients (permission-based)
POST   /api/patients/          # Register new patient
GET    /api/patients/{id}/     # Patient details
PUT    /api/patients/{id}/     # Update patient info
```

#### Sessions
```
GET    /api/sessions/              # List treatment sessions
POST   /api/sessions/              # Record new session
GET    /api/sessions/{id}/         # Session details
PUT    /api/sessions/{id}/         # Update session
```

---

### Appointments
**Base:** `/api/`

#### Appointments
```
GET    /api/appointments/          # List user's appointments
POST   /api/appointments/          # Book appointment
GET    /api/appointments/{id}/     # Appointment details
PUT    /api/appointments/{id}/     # Update appointment
DELETE /api/appointments/{id}/     # Cancel appointment
```

#### Doctor Availability
```
GET    /api/availability/          # List available slots
POST   /api/availability/          # Set availability schedule
GET    /api/availability/{id}/     # Availability details
PUT    /api/availability/{id}/     # Update availability
```

---

### Payments
**Base:** `/api/`

#### Payments
```
GET    /api/payments/          # List payment history
POST   /api/payments/          # Record payment
GET    /api/payments/{id}/     # Payment details
PUT    /api/payments/{id}/     # Update payment
```

---

### Events & Workshops
**Base:** `/api/`

#### Events
```
GET    /api/events/          # List published events
POST   /api/events/          # Create event (admin)
GET    /api/events/{id}/     # Event details
PUT    /api/events/{id}/     # Update event
DELETE /api/events/{id}/     # Delete event
```

---

## Authentication

All protected endpoints require authentication via JWT token.

### Getting an Access Token

Use the `djangorestframework-simplejwt` library to obtain tokens:

```bash
POST /api/token/
```

**Request:**
```json
{
  "username": "user@clinic.com",
  "password": "your_password"
}
```

**Response:**
```json
{
  "access": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc..."
}
```

### Using the Token

Include the token in the `Authorization` header:

```
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGc...
```

---

## Permissions & Access Control

### Role-Based Access

- **Superadmin**: Full access to all endpoints
- **Doctor**: Can manage appointments, patient sessions, availability
- **Receptionist**: Can view appointments, manage bookings
- **Patient**: Can view/update own profile, book appointments, view history

### Permission Classes Used

- `IsSuperAdmin` - Superadmin only
- `IsDoctor` - Doctors and admins
- `IsReceptionist` - All authenticated staff
- `IsOwnerOrAdmin` - Own data or admin
- `IsPatientOwnerOrDoctor` - Patient owns data or doctor can view
- `IsClinicAdmin` - Clinic admin only

---

## Rate Limiting

### OTP Endpoints
- **Request OTP**: Max 3 per hour per user
- **Verify OTP**: Max 5 failed attempts per OTP
- **Daily Limit**: Max 5 OTP requests per day

---

## Error Responses

### 400 Bad Request
```json
{
  "field_name": ["Error message"]
}
```

### 401 Unauthorized
```json
{
  "detail": "Authentication credentials were not provided."
}
```

### 403 Forbidden
```json
{
  "detail": "You do not have permission to perform this action."
}
```

### 404 Not Found
```json
{
  "detail": "Not found."
}
```

### 429 Too Many Requests
```json
{
  "detail": "Request throttled. Retry after X seconds."
}
```

### 500 Internal Server Error
```json
{
  "detail": "Internal server error (details logged)"
}
```

---

## Filtering, Searching & Sorting

Most list endpoints support filtering, searching, and sorting:

### Filtering
```
/api/appointments/?status=confirmed&practitioner=1
```

### Searching
```
/api/patients/?search=John
```

### Sorting
```
/api/appointments/?ordering=-appointment_date
```

---

## Pagination

List endpoints use cursor or page-number pagination:

```
/api/patients/?page=2&page_size=20
```

---

## Development

### Regenerating Schema

If you add new endpoints or modify existing ones:

```bash
python manage.py spectacular --file schema.yml
```

### Testing API Endpoints

Use the interactive Swagger UI at:
```
http://localhost:8000/api/schema/swagger/
```

Or use `curl`:
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:8000/api/patients/
```

Or use `httpie`:
```bash
http -A bearer -a YOUR_TOKEN \
  http://localhost:8000/api/patients/
```

---

## Documentation Standards

All viewsets include docstrings and schema descriptions:

```python
class PatientViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing patient profiles.
    
    list: Get all patients (permission-based filtering)
    create: Register a new patient
    retrieve: Get specific patient
    update: Update patient information
    """
```

---

## Troubleshooting

### Schema Not Updating
Clear the schema cache:
```bash
python manage.py clear_cache
python manage.py spectacular --file schema.yml
```

### Missing Endpoints
Ensure viewsets are registered in `spinalcure/urls.py`:
```python
api_router.register(r'patients', PatientViewSet)
```

### Authentication Not Working
Verify JWT settings in `settings.py`:
```python
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ]
}
```

---

## External Integrations

### Postman
Import the OpenAPI schema directly into Postman:
1. New → API
2. Paste schema URL: `http://localhost:8000/api/schema/`
3. Import

### Swagger Editor
Upload the schema at: https://editor.swagger.io/

### OpenAPI Generators
Generate SDKs using tools like:
- `openapi-generator`
- `swagger-codegen`

---

## Support

For API-related questions or issues:
- Email: `api-support@spinalcure.com`
- Docs: `http://localhost:8000/api/schema/swagger/`

---

**Last Updated:** March 6, 2026  
**drf-spectacular Version:** 0.29.0  
**Python:** 3.13+  
**Django:** 4.2+
