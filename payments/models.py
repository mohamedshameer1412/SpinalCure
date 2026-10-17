from django.db import models
import uuid
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django.core.exceptions import ValidationError
from patients.models import Patient
from decimal import Decimal
from spinalcure.validators import validate_positive_amount, validate_percentage
import random
from datetime import date


class Payment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    """
    Payment records for treatments.
    """
    PAYMENT_MODE_CHOICES = [
        ('cash', _('Cash')),
        ('card', _('Card')),
        ('upi', _('UPI')),
        ('bank_transfer', _('Bank Transfer')),
        ('cheque', _('Cheque')),
        ('other', _('Other')),
    ]
    PAYMENT_STATUS_CHOICES = [
        ('fully_paid', _('Fully Paid')),
        ('partial', _('Partial')),
        ('unpaid', _('Unpaid')),
    ]
    TAX_TYPE_CHOICES = [
        ('none', _('No Tax')),
        ('inclusive', _('Tax Inclusive')),
        ('exclusive', _('Tax Exclusive')),
    ]

    PAYER_TYPE_CHOICES = [
        ('patient', _('Patient')),
        ('student', _('Course Student')),
        ('participant', _('Event Participant')),
    ]

    patient = models.ForeignKey(
        Patient,
        on_delete=models.CASCADE,
        related_name='payments',
        verbose_name=_('Patient'),
        db_index=True,
        null=True,
        blank=True
    )
    payer_type = models.CharField(
        max_length=20,
        choices=PAYER_TYPE_CHOICES,
        default='patient',
        verbose_name=_('Payer Type'),
        db_index=True
    )
    treatment_plan = models.ForeignKey(
        'patients.TreatmentPlan',
        on_delete=models.SET_NULL,
        related_name='payments',
        verbose_name=_('Treatment Plan'),
        null=True,
        blank=True,
        help_text=_('Link this payment to a specific treatment plan')
    )
    # Registration Links
    course_registration = models.ForeignKey(
        'courses.CourseRegistration',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payments',
        verbose_name=_('Course Registration')
    )
    event_registration = models.ForeignKey(
        'events.EventRegistration',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payments',
        verbose_name=_('Event Registration')
    )
    
    # Fallback/Manual details if registration isn't yet created or for non-patient payers
    manual_payer_name = models.CharField(max_length=200, blank=True, verbose_name=_('Payer Name (Manual)'))
    manual_payer_phone = models.CharField(max_length=20, blank=True, verbose_name=_('Payer Phone (Manual)'))

    clinic = models.ForeignKey(
        'clinic.ClinicProfile',
        on_delete=models.CASCADE,
        related_name='payments',
        verbose_name=_('Clinic'),
        null=True,
        blank=True
    )
    collected_by = models.ForeignKey(
        'accounts.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='collected_payments',
        verbose_name=_('Collected By')
    )
    total_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[validate_positive_amount],
        verbose_name=_('Total Amount')
    )
    amount_paid = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[validate_positive_amount],
        verbose_name=_('Amount Paid'),
        help_text=_('Must be less than or equal to total amount')
    )
    payment_mode = models.CharField(
        max_length=20,
        choices=PAYMENT_MODE_CHOICES,
        default='cash',
        verbose_name=_('Payment Mode'),
        db_index=True
    )
    payment_status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default='unpaid',
        verbose_name=_('Status'),
        db_index=True,
        editable=False
    )
    payment_date = models.DateField(
        verbose_name=_('Payment Date'),
        db_index=True,
        default=date.today
    )
    receipt_number = models.CharField(
        max_length=50,
        blank=True,
        unique=True,
        verbose_name=_('Receipt No.'),
        help_text=_('Auto-generated if not provided')
    )
    description = models.CharField(max_length=300, blank=True, verbose_name=_('Description'))
    notes = models.TextField(blank=True)

    # GST / Tax fields
    tax_type = models.CharField(
        max_length=20,
        choices=TAX_TYPE_CHOICES,
        default='none',
        verbose_name=_('Tax Type')
    )
    tax_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        validators=[validate_percentage],
        verbose_name=_('Tax %')
    )

    class Meta:
        verbose_name = _('Payment')
        verbose_name_plural = _('Payments')
        ordering = ['-payment_date']
        indexes = [
            models.Index(fields=['payer_type', 'payment_date']),
            models.Index(fields=['payment_status', 'payment_date']),
        ]

    @property
    def payer_name(self):
        """Getter for the unified payer name."""
        if self.payer_type == 'patient' and self.patient:
            return self.patient.name
        if self.payer_type == 'student' and self.course_registration:
            return self.course_registration.name
        if self.payer_type == 'participant' and self.event_registration:
            return self.event_registration.name
        return self.manual_payer_name or _("Unknown Payer")

    def __str__(self):
        return f"{self.payer_name} — ₹{self.amount_paid}/{self.total_amount} ({self.get_payment_status_display()})"

    @property
    def payer_phone(self):
        """Unified phone number for the payer."""
        if self.payer_type == 'patient' and self.patient:
            return self.patient.phone
        if self.payer_type == 'student' and self.course_registration:
            return self.course_registration.phone
        if self.payer_type == 'participant' and self.event_registration:
            return self.event_registration.phone
        return self.manual_payer_phone or ""

    @property
    def payer_address(self):
        """Unified address for the payer."""
        if self.payer_type == 'patient' and self.patient:
            return self.patient.address
        return ""

    @property
    def balance(self):
        """How much still needs to be paid."""
        return self.total_amount - self.amount_paid

    @property
    def subtotal(self):
        """Amount before tax."""
        if self.tax_type == 'exclusive' and self.tax_percent > 0:
            return self.total_amount
        elif self.tax_type == 'inclusive' and self.tax_percent > 0:
            rate = 1 + (self.tax_percent / Decimal('100'))
            return round(self.total_amount / rate, 2)
        return self.total_amount

    @property
    def tax_amount(self):
        """Calculated tax amount."""
        if self.tax_percent == 0 or self.tax_type == 'none':
            return Decimal('0')
        if self.tax_type == 'exclusive':
            return round(self.total_amount * self.tax_percent / Decimal('100'), 2)
        elif self.tax_type == 'inclusive':
            return round(self.total_amount - self.subtotal, 2)
        return Decimal('0')

    @property
    def grand_total(self):
        """Final total including tax."""
        if self.tax_type == 'exclusive':
            return self.total_amount + self.tax_amount
        return self.total_amount

    def clean(self):
        """Validate payment data."""
        if self.amount_paid > self.total_amount:
            raise ValidationError(
                {'amount_paid': _('Amount paid cannot exceed total amount.')}
            )

    def save(self, *args, **kwargs):
        """Auto-update status and generate receipt number."""
        # Full validation
        self.full_clean()
        
        # Auto-set status based on payment
        if self.amount_paid >= self.total_amount:
            self.payment_status = 'fully_paid'
        elif self.amount_paid > 0:
            self.payment_status = 'partial'
        else:
            self.payment_status = 'unpaid'
        
        # Auto-generate unique receipt number
        if not self.receipt_number:
            while True:
                receipt = f"SC{date.today().strftime('%Y%m%d')}{random.randint(100, 999)}"
                if not Payment.objects.filter(receipt_number=receipt).exists():
                    self.receipt_number = receipt
                    break
        
        super().save(*args, **kwargs)


class Expense(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    """
    Clinic expense tracking.
    """
    CATEGORY_CHOICES = [
        ('rent', _('Rent / Lease')),
        ('salaries', _('Salaries & Wages')),
        ('equipment', _('Equipment & Instruments')),
        ('supplies', _('Medical Supplies')),
        ('utilities', _('Utilities (Electric/Water)')),
        ('marketing', _('Marketing & Advertising')),
        ('maintenance', _('Repairs & Maintenance')),
        ('transport', _('Transport')),
        ('insurance', _('Insurance')),
        ('taxes', _('Taxes & Fees')),
        ('other', _('Other')),
    ]

    title = models.CharField(
        max_length=200,
        verbose_name=_('Title / Description'),
        db_index=True
    )
    category = models.CharField(
        max_length=30,
        choices=CATEGORY_CHOICES,
        default='other',
        verbose_name=_('Category'),
        db_index=True
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[validate_positive_amount],
        verbose_name=_('Amount (₹)')
    )
    expense_date = models.DateField(
        verbose_name=_('Date'),
        db_index=True,
        default=date.today
    )
    paid_to = models.CharField(max_length=200, blank=True, verbose_name=_('Paid To'))
    receipt = models.ImageField(
        upload_to='expenses/',
        blank=True,
        null=True,
        verbose_name=_('Receipt Photo')
    )
    notes = models.TextField(blank=True, verbose_name=_('Notes'))
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='expenses'
    )

    class Meta:
        verbose_name = _('Expense')
        verbose_name_plural = _('Expenses')
        ordering = ['-expense_date']
        indexes = [
            models.Index(fields=['expense_date', 'category']),
        ]

    def __str__(self):
        return f"{self.title} — ₹{self.amount} ({self.expense_date})"

    def clean(self):
        """Validate expense data."""
        from datetime import date
        if self.expense_date > date.today():
            raise ValidationError({'expense_date': _('Expense date cannot be in the future.')})

