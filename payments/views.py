from django.utils.translation import gettext
from django.contrib.auth.decorators import login_required
from spinalcure.rbac import has_capability, capability_rw_permission, require_capability
from patients.search import patient_q
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.db.models import Sum, Q
from django.http import HttpResponse, JsonResponse
from django.core.paginator import Paginator
from spinalcure.utils import SpinalCureExport, log_action
from .models import Payment, Expense, PaymentRefund
from .refunds import refund_payment, RefundError
from patients.models import PatientReview
from rest_framework import viewsets, filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.permissions import IsAuthenticated
from .serializers import PaymentSerializer
from spinalcure.permissions import IsDoctor
import logging
from django.views.decorators.http import require_POST
from spinalcure.decorators import superadmin_required, require_pin_auth

logger = logging.getLogger(__name__)


class PaymentViewSet(viewsets.ModelViewSet):
    """
    ViewSet for payment management.
    Only doctors and admins can view/manage payments.
    """
    queryset = Payment.objects.all().order_by('-payment_date').select_related('patient')
    serializer_class = PaymentSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['patient', 'payment_status', 'payment_mode']
    search_fields = ['patient__name', 'notes', 'receipt_number']
    ordering_fields = ['payment_date', 'amount_paid']
    permission_classes = [IsAuthenticated, capability_rw_permission('billing.view', 'billing.manage')]


@login_required
def payment_list_view(request):
    """List all payments - admin panel."""
    if not has_capability(request.user, 'billing.view'):
        messages.error(request, gettext('You do not have permission to view this page.'))
        return redirect('dashboard')
    
    query = request.GET.get('q', '')
    payments = Payment.objects.all().select_related('patient', 'course_registration', 'event_registration').order_by('-payment_date')
    if query:
        payments = payments.filter(Q(receipt_number__icontains=query) | patient_q(query, 'patient__', ('name',)))
    
    total_collected = payments.aggregate(total=Sum('amount_paid'))['total'] or 0
    
    # Pagination
    paginator = Paginator(payments, 20)  # Show 20 payments per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Export URLs with current search query
    base_export_params = f"?q={query}" if query else ""
    from django.urls import reverse
    
    context = {
        'payments': page_obj,
        'total_collected': total_collected,
        'search_query': query,
        'export_payments_excel_url': reverse('export_payments_excel') + base_export_params,
        'export_payments_csv_url': reverse('export_payments_csv') + base_export_params,
        'export_payments_pdf_url': reverse('export_payments_pdf') + base_export_params,
        'export_payments_copy_url': reverse('export_payments_copy') + base_export_params,
        'export_payments_print_url': reverse('export_payments_print') + base_export_params,
    }

    if request.headers.get('HX-Request'):
        return render(request, 'payments/partials/payment_list_partial.html', context)

    return render(request, 'payments/payment_list.html', context)


@require_capability('billing.manage')
def send_invoice_email_view(request, pk):
    """AJAX view to send professional invoice email to client."""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': gettext('Invalid request method.')}, status=405)
    
    try:
        payment = Payment.objects.get(pk=pk)
        from .utils import send_payment_receipt_email
        success = send_payment_receipt_email(payment, request)
        
        if success:
            return JsonResponse({'status': 'success', 'message': gettext('Email sent successfully.')})
        else:
            return JsonResponse({'status': 'error', 'message': gettext('Recipient has no valid email address.')}, status=400)
    except Payment.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': gettext('Payment record not found.')}, status=404)
    except Exception as e:
        logger.error(f"Error in send_invoice_email_view: {str(e)}")
        return JsonResponse({'status': 'error', 'message': gettext('Could not send the email. Please try again.')}, status=500)


def payment_pdf_download_view(request, pk):
    """Generate and download a ReportLab PDF receipt for a payment (admin or patient)."""
    # Check authorization: either staff/doctor or the patient who owns the payment
    is_staff = has_capability(request.user, 'billing.view')
    patient_id = request.session.get('patient_id')
    
    if not is_staff and not patient_id:
        return redirect('portal_login')

    payment = get_object_or_404(
        Payment.objects.select_related('patient', 'clinic', 'course_registration', 'event_registration'),
        pk=pk
    )

    if not is_staff and str(payment.patient_id) != patient_id:
        messages.error(request, gettext('You do not have permission to download this receipt.'))
        return redirect('portal_dashboard')

    try:
        from .pdf_utils import generate_receipt_pdf
        pdf_bytes = generate_receipt_pdf(payment)
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = (
            f'attachment; filename="receipt_{payment.receipt_number}.pdf"'
        )
        logger.info(f'PDF receipt downloaded for payment {payment.receipt_number} by {request.user.email}')
        return response
    except Exception as e:
        logger.error(f'PDF generation error for payment {pk}: {e}')
        messages.error(request, gettext('Could not generate PDF: %(e)s') % {'e': e})
        return redirect('payment_invoice', pk=pk)


@login_required
def payment_invoice_view(request, pk):
    """Generate a printable GST invoice for a payment."""
    if not has_capability(request.user, 'billing.view'):
        messages.error(request, gettext('You do not have permission to view this page.'))
        return redirect('dashboard')
    
    payment = get_object_or_404(Payment.objects.select_related('patient', 'clinic', 'course_registration', 'event_registration'), pk=pk)
    from clinic.models import ClinicProfile
    from . import razorpay as rzp
    from .models import OnlineOrder
    clinic = ClinicProfile.objects.first()
    
    context = {
        'payment': payment,
        'clinic': clinic,
        'refunds': payment.refunds.select_related('refunded_by'),
        'refund_modes': Payment.PAYMENT_MODE_CHOICES,
        'razorpay_enabled': rzp.enabled(),
        'online_orders': OnlineOrder.objects.filter(payment_ref=str(payment.pk))[:10],
    }
    return render(request, 'payments/invoice.html', context)


@login_required
@require_POST
def payment_refund_view(request, pk):
    if not has_capability(request.user, 'billing.refund'):
        messages.error(request, gettext('You do not have permission to issue refunds.'))
        return redirect('payment_invoice', pk=pk)
    payment = get_object_or_404(Payment, pk=pk)
    try:
        refund = refund_payment(payment.pk, request.POST.get('amount'), request.POST.get('reason'), request.user,
                                request.POST.get('mode', 'cash'))
    except RefundError as e:
        messages.error(request, str(e))
    else:
        log_action(request, 'create', 'PaymentRefund', f'Refund ₹{refund.amount} on {payment.receipt_number}',
                   object_id=refund.id)
        messages.success(request, gettext('Refund of ₹%(amount)s recorded.') % {'amount': refund.amount})
    return redirect('payment_invoice', pk=pk)


@login_required
def payments_report_view(request):
    """Collections, GST, refunds and outstanding dues for a date range (default: this month)."""
    if not has_capability(request.user, 'reports.view'):
        messages.error(request, gettext('You do not have permission to view this page.'))
        return redirect('dashboard')
    from datetime import date, datetime
    from decimal import Decimal
    today = date.today()

    def _d(name, default):
        try:
            return datetime.strptime(request.GET.get(name, ''), '%Y-%m-%d').date()
        except ValueError:
            return default
    start, end = _d('from', today.replace(day=1)), _d('to', today)
    if start > end:
        start, end = end, start
    # one streaming pass (constant memory), so a multi-year range with tens of thousands of payments stays fast
    by_mode, count = {}, 0
    billed = collected = gst = outstanding = Decimal('0')
    for p in Payment.objects.filter(payment_date__range=(start, end)).iterator(chunk_size=2000):
        count += 1
        mode = p.get_payment_mode_display()
        by_mode[mode] = by_mode.get(mode, Decimal('0')) + p.amount_paid
        billed += p.grand_total
        collected += p.amount_paid
        gst += p.tax_amount
        if p.balance > 0:
            outstanding += p.balance
    # aware bounds, not created_at__date: MySQL/MariaDB without timezone tables turns __date into NULL
    from datetime import time, timedelta
    from django.utils import timezone
    lo, hi = (timezone.make_aware(datetime.combine(d, time.min)) for d in (start, end + timedelta(days=1)))
    refunds = PaymentRefund.objects.filter(created_at__gte=lo, created_at__lt=hi)
    refunded = refunds.aggregate(t=Sum('amount'))['t'] or Decimal('0')
    expenses = Expense.objects.filter(expense_date__range=(start, end)).aggregate(t=Sum('amount'))['t'] or Decimal('0')
    return render(request, 'payments/report.html', {
        'start': start, 'end': end, 'count': count, 'billed': billed, 'collected': collected,
        'gst': gst, 'refunded': refunded, 'net': collected - refunded, 'expenses': expenses,
        'outstanding': outstanding, 'profit': collected - refunded - expenses,
        'by_mode': sorted(by_mode.items(), key=lambda kv: -kv[1]), 'refund_rows': refunds.select_related('payment')[:50],
    })


@login_required
def expense_list_view(request):
    """List all expenses - admin panel."""
    if not (request.user.role == 'superadmin' or request.user.is_superuser):
        messages.error(request, gettext('Only admins can view expenses.'))
        return redirect('dashboard')
    
    query = request.GET.get('q', '')
    category = request.GET.get('category', '')
    
    expenses = Expense.objects.all().order_by('-expense_date').select_related('created_by')
    
    if query:
        expenses = expenses.filter(Q(title__icontains=query) | Q(notes__icontains=query) | Q(paid_to__icontains=query))
    
    if category:
        expenses = expenses.filter(category=category)
        
    total_expenses = expenses.aggregate(total=Sum('amount'))['total'] or 0
    from django.utils import timezone
    now = timezone.now()
    monthly_total = Expense.objects.filter(expense_date__month=now.month, expense_date__year=now.year).aggregate(total=Sum('amount'))['total'] or 0

    # Pagination
    paginator = Paginator(expenses, 20)  # Show 20 expenses per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Export URLs with current filters
    params = f"?q={query}&category={category}"
    from django.urls import reverse
    
    context = {
        'expenses': page_obj,
        'total_expenses': total_expenses,
        'monthly_total': monthly_total,
        'categories': Expense.CATEGORY_CHOICES,
        'selected_category': category,
        'search_query': query,
        'export_expenses_excel_url': reverse('export_expenses_excel') + params,
        'export_expenses_csv_url': reverse('export_expenses_csv') + params,
        'export_expenses_pdf_url': reverse('export_expenses_pdf') + params,
        'export_expenses_copy_url': reverse('export_expenses_copy') + params,
        'export_expenses_print_url': reverse('export_expenses_print') + params,
    }
    
    if request.headers.get('HX-Request'):
        return render(request, 'payments/partials/expense_list_partial.html', context)

    return render(request, 'payments/expense_list.html', context)


@login_required
def expense_create_view(request):
    """Create a new expense record."""
    if not (request.user.role == 'superadmin' or request.user.is_superuser):
        messages.error(request, gettext('Only admins can create expenses.'))
        return redirect('dashboard')
    
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        category = request.POST.get('category', 'other')
        amount = request.POST.get('amount', '0')
        expense_date = request.POST.get('expense_date')
        paid_to = request.POST.get('paid_to', '').strip()
        notes = request.POST.get('notes', '').strip()

        if title and amount and expense_date:
            try:
                expense = Expense.objects.create(
                    title=title,
                    category=category,
                    amount=amount,
                    expense_date=expense_date,
                    paid_to=paid_to,
                    notes=notes,
                    created_by=request.user,
                )
                log_action(request, 'create', 'Expense', f'{title} (₹{amount})', object_id=expense.id)
                messages.success(request, gettext('Expense "%(title)s" recorded successfully.') % {'title': title})
                logger.info(f'Expense created by {request.user.email}: {title} (₹{amount})')
                return redirect('expense_list')
            except Exception as e:
                messages.error(request, gettext('Error creating expense: %(value1)s') % {'value1': str(e)})
                logger.error(f'Error creating expense: {str(e)}')
        else:
            messages.error(request, gettext('Please fill in all required fields.'))

    context = {'categories': Expense.CATEGORY_CHOICES}
    return render(request, 'payments/expense_form.html', context)

@login_required
@require_pin_auth('expense_list')
def expense_edit_view(request, pk):
    """Edit an existing expense record."""
    if not has_capability(request.user, 'expenses.manage'):
        messages.error(request, gettext('Only admins and authorized staff can edit expenses.'))
        return redirect('dashboard')
    
    expense = get_object_or_404(Expense, pk=pk)
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        category = request.POST.get('category', 'other')
        amount = request.POST.get('amount', '0')
        expense_date = request.POST.get('expense_date')
        paid_to = request.POST.get('paid_to', '').strip()
        notes = request.POST.get('notes', '').strip()

        if title and amount and expense_date:
            try:
                expense.title = title
                expense.category = category
                expense.amount = amount
                expense.expense_date = expense_date
                expense.paid_to = paid_to
                expense.notes = notes
                expense.save()
                log_action(request, 'update', 'Expense', f'{title} (₹{amount})', object_id=pk)
                messages.success(request, gettext('Expense "%(title)s" updated.') % {'title': title})
                return redirect('expense_list')
            except Exception as e:
                messages.error(request, gettext('Error updating expense: %(value1)s') % {'value1': str(e)})
    
    context = {
        'expense': expense,
        'categories': Expense.CATEGORY_CHOICES,
        'is_edit': True
    }
    return render(request, 'payments/expense_form.html', context)

@login_required
@require_POST
@require_pin_auth('expense_list')
def expense_delete_view(request, pk):
    """Delete an expense record."""
    if not has_capability(request.user, 'expenses.manage'):
        messages.error(request, gettext('Only admins and authorized staff can delete expenses.'))
        return redirect('dashboard')
    
    expense = get_object_or_404(Expense, pk=pk)
    if request.method == 'POST':
        title = expense.title
        amount = expense.amount
        expense_id = expense.id
        expense.delete()
        log_action(request, 'delete', 'Expense', f'{title} (₹{amount})', object_id=expense_id)
        
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.headers.get('Accept') == 'application/json':
            return JsonResponse({'status': 'ok', 'redirect_url': '/en/payments/expenses/'})
            
        messages.success(request, gettext('Expense "%(title)s" deleted.') % {'title': title})
        logger.info(f'Expense deleted by {request.user.email}: {title} (₹{amount})')
    
    return redirect('expense_list')

def _decimal_or_blank(value):
    from decimal import Decimal, InvalidOperation
    try:
        d = Decimal(str(value)[:20])
        return d if d >= 0 else ''
    except (InvalidOperation, ValueError):
        return ''


@login_required
def payment_create_view(request):
    """Record a new payment for Patients, Students (Courses), or Participants (Events)."""
    if not has_capability(request.user, 'billing.manage'):
        messages.error(request, gettext('You do not have permission to perform this action.'))
        return redirect('dashboard')
    
    patient_id = request.GET.get('patient')
    initial_patient = None
    if patient_id:
        from patients.models import Patient
        from spinalcure.utils import decode_b64uuid
        import uuid
        try:
            decoded_id = decode_b64uuid(patient_id)
            if not decoded_id:
                try:
                    decoded_id = uuid.UUID(patient_id)
                except (ValueError, TypeError):
                    pass
            if decoded_id:
                initial_patient = get_object_or_404(Patient, pk=decoded_id)
        except Exception:
            pass

    if request.method == 'POST':
        payer_type = request.POST.get('payer_type', 'patient')
        total_amount = request.POST.get('total_amount')
        amount_paid = request.POST.get('amount_paid', 0)
        payment_mode = request.POST.get('payment_mode')
        payment_date = request.POST.get('payment_date')
        description = request.POST.get('description', '')
        notes = request.POST.get('notes', '')
        
        from clinic.models import ClinicProfile
        clinic = ClinicProfile.objects.first()

        try:
            payment_kwargs = {
                'payer_type': payer_type,
                'total_amount': total_amount,
                'amount_paid': amount_paid,
                'payment_mode': payment_mode,
                'payment_date': payment_date,
                'description': description,
                'notes': notes,
                'clinic': clinic,
                'collected_by': request.user
            }

            if payer_type == 'patient':
                from patients.models import Patient, TreatmentPlan
                patient_id = request.POST.get('patient')
                payment_kwargs['patient'] = get_object_or_404(Patient, pk=patient_id)
                success_redirect = redirect('patient-detail', pk=payment_kwargs['patient'].id)
                payer_name = payment_kwargs['patient'].name
                
                treatment_plan_id = request.POST.get('treatment_plan')
                if treatment_plan_id:
                    payment_kwargs['treatment_plan'] = get_object_or_404(TreatmentPlan, pk=treatment_plan_id)
            
            elif payer_type == 'student':
                from courses.models import CourseBatch, CourseRegistration
                batch_id = request.POST.get('batch')
                batch = get_object_or_404(CourseBatch, pk=batch_id)
                
                name = request.POST.get('student_name')
                phone = request.POST.get('student_phone')
                email = request.POST.get('student_email', '')
                
                # Auto-create registration if it doesn't exist for this batch/email/phone
                reg, created = CourseRegistration.objects.get_or_create(
                    batch=batch, phone=phone,
                    defaults={'name': name, 'email': email}
                )
                payment_kwargs['course_registration'] = reg
                payment_kwargs['manual_payer_name'] = name # Fallback
                success_redirect = redirect('payment_list')
                payer_name = name

            elif payer_type == 'participant':
                from events.models import Event, EventRegistration
                event_id = request.POST.get('event')
                event = get_object_or_404(Event, pk=event_id)
                
                name = request.POST.get('participant_name')
                phone = request.POST.get('participant_phone')
                email = request.POST.get('participant_email', '')
                
                # Auto-create registration
                reg, created = EventRegistration.objects.get_or_create(
                    event=event, phone=phone,
                    defaults={'name': name, 'email': email}
                )
                payment_kwargs['event_registration'] = reg
                payment_kwargs['manual_payer_name'] = name # Fallback
                success_redirect = redirect('payment_list')
                payer_name = name

            payment = Payment.objects.create(**payment_kwargs)
            log_action(request, 'create', 'Payment', f'₹{amount_paid} for {payer_name}', object_id=payment.id)
            
            # Send automated email receipt
            from .utils import send_payment_receipt_email
            send_payment_receipt_email(payment)

            messages.success(request, gettext('Payment of ₹%(amount_paid)s recorded for %(payer_name)s. Email receipt sent.') % {'amount_paid': amount_paid, 'payer_name': payer_name})
            return success_redirect

        except Exception as e:
            messages.error(request, gettext('Error recording payment: %(value1)s') % {'value1': str(e)})

    from patients.models import Patient, TreatmentPlan
    from courses.models import CourseBatch
    from events.models import Event
    from datetime import date
    
    treatment_plans = []
    if initial_patient:
        treatment_plans = initial_patient.treatment_plans.all().order_by('-created_at')

    context = {
        'patients': Patient.objects.all().order_by('name'),
        'batches': CourseBatch.objects.select_related('course').filter(is_active=True).order_by('course__title'),
        'events': Event.objects.filter(date__gte=date.today()).order_by('date'),
        'initial_patient': initial_patient,
        'treatment_plans': treatment_plans,
        # from a package's "Record payment" button
        'prefill_plan': request.GET.get('plan', '')[:40],
        'prefill_amount': _decimal_or_blank(request.GET.get('amount', '')),
        'payment_modes': Payment.PAYMENT_MODE_CHOICES,
        'tax_types': Payment.TAX_TYPE_CHOICES,
        'current_date': date.today(),
    }
    return render(request, 'payments/payment_form.html', context)


@login_required
@require_pin_auth('payment_list')
def payment_edit_view(request, pk):
    """Edit an existing payment record."""
    if not has_capability(request.user, 'billing.manage'):
        messages.error(request, gettext('You do not have permission to perform this action.'))
        return redirect('dashboard')
    
    payment = get_object_or_404(Payment, pk=pk)
    
    if request.method == 'POST':
        try:
            payer_type = request.POST.get('payer_type', payment.payer_type)
            payment.payer_type = payer_type
            payment.total_amount = request.POST.get('total_amount')
            payment.amount_paid = request.POST.get('amount_paid')
            payment.payment_mode = request.POST.get('payment_mode')
            payment.payment_date = request.POST.get('payment_date')
            payment.description = request.POST.get('description', '')
            payment.notes = request.POST.get('notes', '')

            if payer_type == 'patient':
                from patients.models import Patient, TreatmentPlan
                patient_id = request.POST.get('patient')
                if patient_id:
                    payment.patient = get_object_or_404(Patient, pk=patient_id)
                treatment_plan_id = request.POST.get('treatment_plan')
                if treatment_plan_id:
                    payment.treatment_plan = get_object_or_404(TreatmentPlan, pk=treatment_plan_id)
                else:
                    payment.treatment_plan = None
            
            elif payer_type == 'student':
                from courses.models import CourseBatch, CourseRegistration
                batch_id = request.POST.get('batch')
                name = request.POST.get('student_name')
                phone = request.POST.get('student_phone')
                email = request.POST.get('student_email', '')
                
                if batch_id and phone:
                    batch = get_object_or_404(CourseBatch, pk=batch_id)
                    reg, _ = CourseRegistration.objects.get_or_create(
                        batch=batch, phone=phone,
                        defaults={'name': name, 'email': email}
                    )
                    payment.course_registration = reg
                payment.manual_payer_name = name
                payment.manual_payer_phone = phone

            elif payer_type == 'participant':
                from events.models import Event, EventRegistration
                event_id = request.POST.get('event')
                name = request.POST.get('participant_name')
                phone = request.POST.get('participant_phone')
                email = request.POST.get('participant_email', '')
                
                if event_id and phone:
                    event = get_object_or_404(Event, pk=event_id)
                    reg, _ = EventRegistration.objects.get_or_create(
                        event=event, phone=phone,
                        defaults={'name': name, 'email': email}
                    )
                    payment.event_registration = reg
                payment.manual_payer_name = name
                payment.manual_payer_phone = phone

            payment.save()
            log_action(request, 'update', 'Payment', f'Receipt #{payment.receipt_number}', object_id=pk)
            
            messages.success(request, gettext('Payment record updated successfully.'))
            if payment.patient:
                return redirect('patient-detail', pk=payment.patient.id)
            return redirect('payment_list')
        except Exception as e:
            messages.error(request, gettext('Error updating payment: %(value1)s') % {'value1': str(e)})

    from patients.models import Patient, TreatmentPlan
    from courses.models import CourseBatch
    from events.models import Event
    
    treatment_plans = []
    if payment.patient:
        treatment_plans = payment.patient.treatment_plans.all().order_by('-created_at')

    context = {
        'payment': payment,
        'patients': Patient.objects.all().order_by('name'),
        'batches': CourseBatch.objects.all().select_related('course'),
        'events': Event.objects.all(),
        'treatment_plans': treatment_plans,
        'payment_modes': Payment.PAYMENT_MODE_CHOICES,
        'tax_types': Payment.TAX_TYPE_CHOICES,
        'is_edit': True,
        'initial_patient': payment.patient,
    }
    return render(request, 'payments/payment_form.html', context)


@login_required
@require_POST
@require_pin_auth('payment_list')
def payment_delete_view(request, pk):
    """Delete a payment record (management only; a refund is the normal way to reverse money)."""
    if not has_capability(request.user, 'billing.refund'):
        messages.error(request, gettext('You do not have permission to delete payments.'))
        return redirect('payment_list')
    payment = get_object_or_404(Payment, pk=pk)
    patient_id = payment.patient.id if payment.patient else None
    
    if request.method == 'POST':
        receipt = payment.receipt_number
        payment_id = payment.id
        payment.delete()
        log_action(request, 'delete', 'Payment', f'Receipt #{receipt}', object_id=payment_id)
        
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.headers.get('Accept') == 'application/json':
            from django.urls import reverse
            redirect_url = reverse('patient-detail', kwargs={'pk': patient_id}) if patient_id else reverse('payment_list')
            return JsonResponse({'status': 'ok', 'redirect_url': redirect_url})
        messages.success(request, gettext('Payment %(receipt)s deleted successfully.') % {'receipt': receipt})
        if patient_id:
            return redirect('patient-detail', pk=patient_id)
        return redirect('payment_list')
    
    if patient_id:
        return redirect('patient-detail', pk=patient_id)
    return redirect('payment_list')

def _get_filtered_expenses(request):
    query = request.GET.get('q', '')
    cat = request.GET.get('category', '')
    expenses = Expense.objects.all().order_by('-expense_date')
    if query:
        expenses = expenses.filter(Q(title__icontains=query) | Q(paid_to__icontains=query))
    if cat:
        expenses = expenses.filter(category=cat)
    return expenses, query

def _expense_mapping(e):
    return [e.title, e.get_category_display(), float(e.amount), e.expense_date.strftime('%Y-%m-%d'), e.paid_to, e.notes]

@require_capability('expenses.manage')
def export_expenses_excel(request):
    expenses, _ = _get_filtered_expenses(request)
    headers = ["Title", "Category", "Amount", "Date", "Paid To", "Notes"]
    return SpinalCureExport.to_excel(expenses, headers, _expense_mapping, "Expenses", "expenses")

@require_capability('expenses.manage')
def export_expenses_csv(request):
    expenses, _ = _get_filtered_expenses(request)
    headers = ["Title", "Category", "Amount", "Date", "Paid To", "Notes"]
    return SpinalCureExport.to_csv(expenses, headers, _expense_mapping, "expenses")

@require_capability('expenses.manage')
def export_expenses_pdf(request):
    expenses, query = _get_filtered_expenses(request)
    headers = ["Title", "Category", "Amount", "Date", "Paid To"]
    def pdf_mapping(e):
        return [e.title, e.get_category_display(), f"₹{e.amount:,.2f}", e.expense_date.strftime('%Y-%m-%d'), e.paid_to]
    title = f"Expense Report {'(Filtered)' if query else ''}"
    return SpinalCureExport.to_pdf(expenses, headers, pdf_mapping, title, "expenses")

@require_capability('expenses.manage')
def export_expenses_copy(request):
    expenses, _ = _get_filtered_expenses(request)
    headers = ["Title", "Category", "Amount", "Date", "Paid To"]
    text = SpinalCureExport.to_text(expenses, headers, _expense_mapping)
    return HttpResponse(text, content_type='text/plain')

@require_capability('expenses.manage')
def export_expenses_print(request):
    expenses, query = _get_filtered_expenses(request)
    headers = ["Title", "Category", "Amount", "Date", "Paid To"]
    rows = [[e.title, e.get_category_display(), f"₹{e.amount:,.2f}", e.expense_date.strftime('%Y-%m-%d'), e.paid_to] for e in expenses]
    from datetime import datetime
    context = {
        'rows': rows,
        'title': 'Expense Report',
        'query': query,
        'headers': headers,
        'now': datetime.now(),
    }
    return render(request, 'exports/print_template.html', context)

# ── Payment Export Logic ──

def get_payer_name(payment):
    if payment.patient:
        return payment.patient.name
    if payment.manual_payer_name:
        return payment.manual_payer_name
    if payment.course_registration:
        return payment.course_registration.student_name
    if payment.event_registration:
        return payment.event_registration.participant_name
    return "N/A"

def _get_filtered_payments(request):
    query = request.GET.get('q', '')
    payments = Payment.objects.all().select_related('patient', 'course_registration', 'event_registration').order_by('-payment_date')
    if query:
        payments = payments.filter(
            Q(receipt_number__icontains=query) |
            patient_q(query, 'patient__', ('name',)) |
            Q(manual_payer_name__icontains=query)
        )
    return payments, query

def _payment_mapping(payment):
    return [
        payment.receipt_number,
        payment.payment_date.strftime('%Y-%m-%d'),
        get_payer_name(payment),
        float(payment.amount_paid),
        float(payment.total_amount),
        payment.get_payment_mode_display(),
        payment.get_payment_status_display()
    ]

@require_capability('billing.view')
def export_payments_excel(request):
    payments, _ = _get_filtered_payments(request)
    headers = ["Receipt No", "Date", "Payer Name", "Amount Paid", "Total Amount", "Mode", "Status"]
    return SpinalCureExport.to_excel(payments, headers, _payment_mapping, "Payments", "payments")

@require_capability('billing.view')
def export_payments_csv(request):
    payments, _ = _get_filtered_payments(request)
    headers = ["Receipt No", "Date", "Payer Name", "Amount Paid", "Total Amount", "Mode", "Status"]
    return SpinalCureExport.to_csv(payments, headers, _payment_mapping, "payments")

@require_capability('billing.view')
def export_payments_pdf(request):
    payments, query = _get_filtered_payments(request)
    headers = ["Receipt No", "Date", "Payer Name", "Amount", "Mode", "Status"]
    def pdf_mapping(p):
        return [
            p.receipt_number,
            p.payment_date.strftime('%Y-%m-%d'),
            get_payer_name(p),
            f"₹{p.amount_paid:,.2f}",
            p.get_payment_mode_display(),
            p.get_payment_status_display()
        ]
    title = f"Payments Report {'(Filtered)' if query else ''}"
    return SpinalCureExport.to_pdf(payments, headers, pdf_mapping, title, "payments")

@require_capability('billing.view')
def export_payments_copy(request):
    payments, _ = _get_filtered_payments(request)
    headers = ["Receipt No", "Date", "Payer Name", "Paid", "Total", "Mode", "Status"]
    text = SpinalCureExport.to_text(payments, headers, _payment_mapping)
    return HttpResponse(text, content_type='text/plain')

@require_capability('billing.view')
def export_payments_print(request):
    payments, query = _get_filtered_payments(request)
    headers = ["Receipt", "Date", "Payer", "Amount", "Mode", "Status"]
    rows = [[p.receipt_number, p.payment_date.strftime('%Y-%m-%d'), get_payer_name(p), f"₹{p.amount_paid:,.2f}", p.get_payment_mode_display(), p.get_payment_status_display()] for p in payments]
    from datetime import datetime
    context = {
        'rows': rows,
        'title': 'Payments Report',
        'query': query,
        'headers': headers,
        'now': datetime.now(),
    }
    return render(request, 'exports/print_template.html', context)
