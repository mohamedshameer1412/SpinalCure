from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from patients.models import Patient, Session
from payments.models import Payment, Expense
from appointments.models import Appointment
from django.db.models import Sum, Count, Q, Avg
from django.db.models.functions import TruncMonth, TruncDate
from datetime import date, timedelta
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated


class DashboardStatsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        today = date.today()
        total_patients = Patient.objects.count()
        sessions_today = Session.objects.filter(session_date=today).count()
        revenue_today = Payment.objects.filter(payment_date=today).aggregate(total=Sum('amount_paid'))['total'] or 0
        upcoming = Appointment.objects.filter(appointment_date__gte=today, status='scheduled').count()

        return Response({
            'total_patients': total_patients,
            'sessions_today': sessions_today,
            'revenue_today': revenue_today,
            'upcoming_appointments': upcoming
        })


@login_required
def dashboard_view(request):
    today = date.today()
    thirty_days_ago = today - timedelta(days=30)
    six_months_ago = today - timedelta(days=180)
    year_ago = today - timedelta(days=365)

    # ── Quick Stats ────────────────────────────────────────────────────────
    total_patients = Patient.objects.count()
    sessions_today = Session.objects.filter(session_date=today).count()
    revenue_today = Payment.objects.filter(payment_date=today).aggregate(total=Sum('amount_paid'))['total'] or 0
    expenses_today = Expense.objects.filter(expense_date=today).aggregate(total=Sum('amount'))['total'] or 0
    upcoming_appointments = Appointment.objects.filter(
        appointment_date__gte=today, status='scheduled'
    ).select_related('patient', 'practitioner').order_by('appointment_date', 'appointment_time')[:5]

    # ── New Stats: Pending Dues ────────────────────────────────────────────
    # GST-exclusive payments owe total + tax, so the balance is computed on the model, not in SQL.
    pending_dues = sum((p.balance for p in Payment.objects.filter(payment_status__in=['partial', 'unpaid'])), 0)

    # ── New Stats: No-Show Rate ────────────────────────────────────────────
    total_past_appts = Appointment.objects.filter(
        appointment_date__lt=today
    ).count()
    no_show_count = Appointment.objects.filter(
        appointment_date__lt=today, status='no_show'
    ).count()
    no_show_rate = round((no_show_count / total_past_appts * 100), 1) if total_past_appts > 0 else 0

    # ── New Stats: Top Practitioner (by sessions this month) ──────────────
    from clinic.models import Practitioner
    top_practitioner = Session.objects.filter(
        session_date__month=today.month,
        session_date__year=today.year,
        consulted_by__isnull=False,
    ).values('consulted_by__name').annotate(
        count=Count('id')
    ).order_by('-count').first()

    top_practitioner_name = top_practitioner['consulted_by__name'] if top_practitioner else '—'
    top_practitioner_sessions = top_practitioner['count'] if top_practitioner else 0

    # ── Chart 1: Revenue last 30 days ─────────────────────────────────────
    revenue_chart_data = Payment.objects.filter(payment_date__gte=thirty_days_ago) \
        .values('payment_date') \
        .annotate(total=Sum('amount_paid')) \
        .order_by('payment_date')

    # ── Chart 2: Sessions per month (last 12 months) ──────────────────────
    sessions_chart_data = Session.objects.filter(session_date__gte=year_ago) \
        .annotate(month=TruncMonth('session_date')) \
        .values('month') \
        .annotate(count=Count('id')) \
        .order_by('month')

    # ── Chart 3: Expenses last 30 days ────────────────────────────────────
    expense_chart_data = Expense.objects.filter(expense_date__gte=thirty_days_ago) \
        .values('expense_date') \
        .annotate(total=Sum('amount')) \
        .order_by('expense_date')

    # ── Chart 4 (NEW): Monthly P&L — Revenue vs Expenses last 6 months ───
    revenue_monthly = Payment.objects.filter(payment_date__gte=six_months_ago) \
        .annotate(month=TruncMonth('payment_date')) \
        .values('month') \
        .annotate(total=Sum('amount_paid')) \
        .order_by('month')

    expense_monthly = Expense.objects.filter(expense_date__gte=six_months_ago) \
        .annotate(month=TruncMonth('expense_date')) \
        .values('month') \
        .annotate(total=Sum('amount')) \
        .order_by('month')

    # ── Chart 5 (NEW): Payment mode breakdown ─────────────────────────────
    payment_mode_data = Payment.objects.filter(
        payment_date__gte=thirty_days_ago
    ).values('payment_mode').annotate(count=Count('id')).order_by('-count')

    # ── Chart 6 (NEW): New patients per month (last 6 months) ─────────────
    new_patients_monthly = Patient.objects.filter(registered_date__gte=six_months_ago) \
        .annotate(month=TruncMonth('registered_date')) \
        .values('month') \
        .annotate(count=Count('id')) \
        .order_by('month')

    context = {
        # Quick stats
        'total_patients': total_patients,
        'sessions_today': sessions_today,
        'revenue_today': revenue_today,
        'expenses_today': expenses_today,
        'upcoming_appointments': upcoming_appointments,
        # New stat cards
        'pending_dues': pending_dues,
        'no_show_rate': no_show_rate,
        'top_practitioner_name': top_practitioner_name,
        'top_practitioner_sessions': top_practitioner_sessions,
        # Existing charts
        'revenue_chart_data': list(revenue_chart_data),
        'sessions_chart_data': list(sessions_chart_data),
        'expense_chart_data': list(expense_chart_data),
        # New charts
        'revenue_monthly': list(revenue_monthly),
        'expense_monthly': list(expense_monthly),
        'payment_mode_data': list(payment_mode_data),
        'new_patients_monthly': list(new_patients_monthly),
    }
    return render(request, 'analytics/dashboard.html', context)
