from django.db import models
import uuid
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django.core.exceptions import ValidationError
from patients.models import Patient
from decimal import Decimal, ROUND_HALF_UP
from django.core.validators import MinValueValidator
from django.db import transaction
from spinalcure.validators import validate_positive_amount, validate_percentage
from datetime import date

TWO = Decimal('0.01')


def money(v):
    return Decimal(v).quantize(TWO, rounding=ROUND_HALF_UP)


def financial_year(d):
    """Indian FY label for a date: April-March, e.g. 2026-27."""
    start = d.year if d.month >= 4 else d.year - 1
    return f'{start}-{str(start + 1)[-2:]}'


class InvoiceCounter(models.Model):
    """Last invoice serial per financial year (GST invoices must be consecutive)."""
    fy = models.CharField(max_length=7, primary_key=True)
    last = models.PositiveIntegerField(default=0)

    @classmethod
    def next_number(cls, d):
        fy = financial_year(d)
        with transaction.atomic():
            cls.objects.get_or_create(fy=fy)
            row = cls.objects.select_for_update().get(fy=fy)
            row.last += 1
            row.save(update_fields=['last'])
        return f'SC/{fy}/{row.last:05d}'


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
        validators=[MinValueValidator(0)],
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
    is_interstate = models.BooleanField(
        default=False, verbose_name=_('Inter-state supply (IGST)'),
        help_text=_('Leave off for customers in the clinic\'s state: tax is split into CGST + SGST')
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
    def refunded_amount(self):
        return money(sum((r.amount for r in self.refunds.all()), Decimal('0')))

    @property
    def balance(self):
        """Still owed, including exclusive GST."""
        return money(self.grand_total - (self.amount_paid or 0))

    @property
    def subtotal(self):
        """Taxable value (before GST)."""
        total = Decimal(self.total_amount or 0)
        if self.tax_type == 'inclusive' and self.tax_percent:
            return money(total / (1 + Decimal(self.tax_percent) / 100))
        return money(total)

    @property
    def tax_amount(self):
        if self.tax_type == 'none' or not self.tax_percent:
            return Decimal('0.00')
        if self.tax_type == 'exclusive':
            return money(Decimal(self.total_amount) * Decimal(self.tax_percent) / 100)
        return money(Decimal(self.total_amount) - self.subtotal)

    @property
    def cgst(self):
        return Decimal('0.00') if self.is_interstate else money(self.tax_amount / 2)

    @property
    def sgst(self):
        # Remainder, so CGST + SGST always equals the tax exactly.
        return Decimal('0.00') if self.is_interstate else self.tax_amount - self.cgst

    @property
    def igst(self):
        return self.tax_amount if self.is_interstate else Decimal('0.00')

    @property
    def half_rate(self):
        return Decimal(self.tax_percent) / 2

    @property
    def grand_total(self):
        """Invoice total including GST."""
        total = money(self.total_amount or 0)
        return total + self.tax_amount if self.tax_type == 'exclusive' else total

    def clean(self):
        if self.tax_type == 'none':
            self.tax_percent = Decimal('0')
        elif not self.tax_percent:
            raise ValidationError({'tax_percent': _('Enter the GST rate, or choose "No Tax".')})
        if self.total_amount is not None and self.amount_paid is not None and Decimal(self.amount_paid) > self.grand_total:
            raise ValidationError({'amount_paid': _('Amount paid cannot exceed the invoice total.')})

    def save(self, *args, **kwargs):
        """Validate, set status from amounts and assign the next invoice number."""
        self.full_clean(exclude=['receipt_number'])
        paid = Decimal(self.amount_paid or 0)
        if paid >= self.grand_total:
            self.payment_status = 'fully_paid'
        elif paid > 0:
            self.payment_status = 'partial'
        else:
            self.payment_status = 'unpaid'
        with transaction.atomic():  # a failed save must not consume an invoice number
            if not self.receipt_number:
                d = self.payment_date if isinstance(self.payment_date, date) else date.fromisoformat(str(self.payment_date))
                self.receipt_number = InvoiceCounter.next_number(d)
            super().save(*args, **kwargs)


class PaymentItem(models.Model):
    """Invoice line. When an invoice has items, its total_amount is the sum of the lines."""
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name='items')
    description = models.CharField(max_length=200, verbose_name=_('Description'))
    sac_code = models.CharField(max_length=8, blank=True, verbose_name=_('SAC/HSN'))
    quantity = models.DecimalField(max_digits=8, decimal_places=2, default=1, validators=[validate_positive_amount])
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])

    @property
    def line_total(self):
        return money(self.quantity * self.unit_price)


class Refund(models.Model):
    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, related_name='refunds')
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[validate_positive_amount])
    refund_date = models.DateField(default=date.today)
    mode = models.CharField(max_length=20, choices=Payment.PAYMENT_MODE_CHOICES, default='cash')
    reason = models.CharField(max_length=300)
    created_by = models.ForeignKey('accounts.CustomUser', on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-refund_date']

    def clean(self):
        if self.payment_id and self.amount:
            already = sum((r.amount for r in self.payment.refunds.exclude(pk=self.pk)), Decimal('0'))
            if already + Decimal(self.amount) > Decimal(self.payment.amount_paid):
                raise ValidationError({'amount': _('Refunds cannot exceed the amount paid.')})


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

