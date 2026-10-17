# SpinalCure Internationalization (i18n) Setup Guide

## Overview

SpinalCure supports multiple languages to serve patients and staff in different regions:
- **Arabic (ar)** - For Arabic-speaking patients and staff
- **Hindi (hi)** - For Hindi-speaking patients and staff  
- **Tamil (ta)** - For Tamil-speaking patients and staff
- **English (en)** - Default language (always available)

## Current Setup

### Directory Structure
```
locale/
├── ar/                    # Arabic translations
│   └── LC_MESSAGES/
│       ├── django.po      # Translation file (human-readable)
│       └── django.mo      # Compiled translations (binary)
├── hi/                    # Hindi translations
│   └── LC_MESSAGES/
│       ├── django.po
│       └── django.mo
└── ta/                    # Tamil translations
    └── LC_MESSAGES/
        ├── django.po
        └── django.mo
```

### Django Settings (settings/base.py)

I18n is configured with:

```python
LANGUAGE_CODE = 'en-us'

LANGUAGES = [
    ('en', 'English'),
    ('ar', 'العربية'),
    ('hi', 'हिन्दी'),
    ('ta', 'தமிழ்'),
]

LOCALE_PATHS = [
    os.path.join(BASE_DIR, 'locale'),
]

USE_I18N = True
USE_L10N = True
TIME_ZONE = 'UTC'
USE_TZ = True
```

### URL Configuration

Language prefix routing is enabled in `spinalcure/urls.py`:

```python
from django.conf.urls.i18n import i18n_patterns

urlpatterns += i18n_patterns(
    # All localized URLs have language prefix:
    # /en/accounts/login/
    # /ar/accounts/login/
    # /hi/accounts/login/
    # /ta/accounts/login/
)
```

---

## Setting Up Translations

### Step 1: Create Translation Files

Generate `.po` (portable object) files for each language:

```bash
# Create translation files for all languages
python manage.py makemessages -l ar -l hi -l ta

# Or create for individual language:
python manage.py makemessages -l ar
```

This scans your code for `_()`, `_lazy()`, `pgettext()` calls and creates `.po` files.

### Step 2: Translate Strings

Edit the `.po` files in `locale/{lang}/LC_MESSAGES/django.po`:

**Example Arabic translation (locale/ar/LC_MESSAGES/django.po):**
```
#: accounts/models.py:15
msgid "Email Verified"
msgstr "تم التحقق من البريد الإلكتروني"

#: accounts/models.py:45
msgid "Password Reset"
msgstr "إعادة تعيين كلمة المرور"
```

**Example Hindi translation (locale/hi/LC_MESSAGES/django.po):**
```
#: accounts/models.py:15
msgid "Email Verified"
msgstr "ईमेल सत्यापित"

#: accounts/models.py:45
msgid "Password Reset"
msgstr "पासवर्ड रीसेट करें"
```

**Example Tamil translation (locale/ta/LC_MESSAGES/django.po):**
```
#: accounts/models.py:15
msgid "Email Verified"
msgstr "மின்னஞ்சல் சரிபார்க்கப்பட்டது"

#: accounts/models.py:45
msgid "Password Reset"
msgstr "கடவுச்சொல்லை மீட்டமைக்கவும்"
```

### Step 3: Compile Translations

Convert `.po` files to `.mo` (machine object) binary files:

```bash
python manage.py compilemessages
```

This creates `.mo` files that Django uses at runtime.

### Step 4: Verify Translations

Restart Django server and test the language switcher:

- English: `http://localhost:8000/en/accounts/login/`
- Arabic: `http://localhost:8000/ar/accounts/login/`
- Hindi: `http://localhost:8000/hi/accounts/login/`
- Tamil: `http://localhost:8000/ta/accounts/login/`

---

## Using Translations in Code

### In Django Templates

```html
<!-- Load translation tags -->
{% load i18n %}

<!-- Translate a string -->
<h1>{% trans "Welcome to SpinalCure" %}</h1>

<!-- Lazy translation (for lazy evaluation) -->
<p>{% trans "Your appointment is confirmed" %}</p>

<!-- Pluralization -->
{% blocktrans count counter=appointment_count %}
    You have {{ counter }} appointment
{% plural %}
    You have {{ counter }} appointments
{% endblocktrans %}
```

### In Python Code (Models/Views)

```python
from django.utils.translation import gettext_lazy as _

class Patient(models.Model):
    name = models.CharField(
        max_length=200,
        verbose_name=_('Patient Name')  # Translatable
    )
    
    class Meta:
        verbose_name = _('Patient')
        verbose_name_plural = _('Patients')

# In views
from django.utils.translation import gettext as _

def book_appointment(request):
    message = _('Appointment booked successfully')
    return JsonResponse({'message': message})
```

### In Forms

```python
from django import forms
from django.utils.translation import gettext_lazy as _

class AppointmentForm(forms.ModelForm):
    class Meta:
        model = Appointment
        fields = ['date', 'time']
        labels = {
            'date': _('Appointment Date'),
            'time': _('Appointment Time'),
        }
        help_texts = {
            'date': _('Select your preferred date'),
        }
```

---

## Key Translatable Strings

### Accounts & Authentication
- "Email Verified"
- "Password Reset"
- "Login"
- "Register"
- "Forgot Password?"
- "Invalid credentials"

### Appointments
- "Book Appointment"
- "Appointment Confirmed"
- "Cancel Appointment"
- "Reschedule"
- "Available Slots"
- "No availability"

### Patient Management
- "Patient Name"
- "Phone Number"
- "Medical History"
- "Treatment Notes"
- "Session Number"

### Payments
- "Payment Receipt"
- "Amount Paid"
- "Balance Due"
- "Tax Percent"
- "Payment Method"

### Clinic
- "Clinic Profile"
- "Practitioner"
- "Specialization"
- "Experience"
- "Bio"

---

## Language Switching

### URL-Based (Built-in)
Language is automatically switched via URL prefix:
```
/en/patients/  → English
/ar/patients/  → Arabic
/hi/patients/  → Hindi
/ta/patients/  → Tamil
```

### Cookie/Session-Based (Optional)

Add language switch template:
```html
<form action="{% url 'django.views.i18n.set_language' %}" method="post">
    {% csrf_token %}
    <select name="language" onchange="this.form.submit()">
        <option value="en" {% if LANGUAGE_CODE == 'en' %}selected{% endif %}>English</option>
        <option value="ar" {% if LANGUAGE_CODE == 'ar' %}selected{% endif %}>العربية</option>
        <option value="hi" {% if LANGUAGE_CODE == 'hi' %}selected{% endif %}>हिन्दी</option>
        <option value="ta" {% if LANGUAGE_CODE == 'ta' %}selected{% endif %}>தமிழ்</option>
    </select>
</form>
```

---

## Email Translations

Email templates can also be translated:

```python
# In api_views.py
from django.utils.translation import gettext as _

subject = _('Password Reset Code')
email_template = _('''
    Hello {name},
    Your OTP is: {otp}
''')
```

Or use language-specific templates:
```
templates/
├── emails/
│   ├── password_reset.en.html
│   ├── password_reset.ar.html
│   ├── password_reset.hi.html
│   └── password_reset.ta.html
```

---

## Best Practices

### 1. Mark Strings as Translatable Early
```python
# Good
verbose_name = _('Patient Name')

# Bad
verbose_name = 'Patient Name'
```

### 2. Use Lazy Translation for Model Fields
```python
from django.utils.translation import gettext_lazy as _

# Use _() for models (evaluated at runtime)
verbose_name = _('Patient')
```

### 3. Keep Strings Simple
```python
# Good - simple and clear
message = _('Appointment confirmed')

# Bad - complex with logic
message = _('Appointment for %s is confirmed on %s' % (name, date))
```

For complex strings, use string formatting:
```python
message = _('Appointment for {name} is confirmed').format(name=user.name)
```

### 4. Use Pluralization
```python
from django.utils.translation import ngettext

count = appointment_count
message = ngettext(
    'You have %(count)d appointment',
    'You have %(count)d appointments',
    count
) % {'count': count}
```

### 5. Never Translate User-Generated Content
Only translate hardcoded strings, not dynamic data:
```python
# Good - translate fixed strings
title = _('Patient Review')

# Bad - don't translate user content
review_text = _(user_input)  # Wrong!
```

---

## Maintenance

### Regular Updates

When code changes, update translations:

```bash
# Find new translatable strings
python manage.py makemessages -l ar -l hi -l ta --add-location=file --no-wrap

# Fuzzy-mark updated translations for review
python manage.py makemessages -l ar -l hi -l ta --update-only

# Recompile after translations are updated
python manage.py compilemessages
```

### Translation Quality

- Use professional translators for production
- Test all language variants
- Check RTL support for Arabic
- Verify font support for Hindi/Tamil
- Test email templates in all languages

### Performance

- Translations are cached at Django startup
- Use `django-modeltranslation` for complex multi-language fields
- Consider lazy translation for large string sets

---

## Testing Translations

### Manual Testing
```bash
# Test each language
curl -H "Accept-Language: ar" http://localhost:8000/
curl -H "Accept-Language: hi" http://localhost:8000/
curl -H "Accept-Language: ta" http://localhost:8000/

# Or use curl with language cookie
curl -b "django_language=ar" http://localhost:8000/
```

### Automated Testing
```python
from django.test import TestCase
from django.utils.translation import override

class TranslationTest(TestCase):
    def test_arabic_translation(self):
        with override('ar'):
            from accounts.models import CustomUser
            self.assertEqual(CustomUser._meta.verbose_name, 'مستخدم')
```

---

## Troubleshooting

### Translations Not Showing
1. Ensure `.mo` files are compiled: `python manage.py compilemessages`
2. Restart Django server
3. Clear browser cache
4. Check language code in URL: `/ar/`, `/hi/`, `/ta/`

### Missing Translations
1. Run: `python manage.py makemessages -a`
2. Edit `.po` files and add translations
3. Recompile: `python manage.py compilemessages`

### Character Encoding Issues
Ensure UTF-8 encoding:
- `.po` files must be UTF-8
- Database should be UTF-8
- HTML templates should have `<meta charset="UTF-8">`

---

## External Tools

### Translation Platforms
- **Weblate**: Open-source platform (self-hosted)
- **CrowdIn**: Cloud-based translation management
- **Lokalise**: Professional translation workspace
- **POEditor**: Simple po/ file editor

### IDE Integration
- VS Code: "Gettext" extension
- PyCharm: Built-in translations support
- Sublime: Better syntax highlighting

---

## Next Steps

1. **Extract Strings**: Run `python manage.py makemessages -l ar -l hi -l ta`
2. **Add Translations**: Edit `.po` files with professional translations
3. **Compile**: Run `python manage.py compilemessages`
4. **Test**: Verify all languages work correctly
5. **Deploy**: Include `.mo` files in production builds

---

**Last Updated:** March 6, 2026  
**Django i18n Version:** Built-in  
**Supported Languages:** English, Arabic, Hindi, Tamil
