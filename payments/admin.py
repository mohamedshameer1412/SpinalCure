from django.contrib import admin
from .models import Payment

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('patient', 'receipt_number', 'payment_date', 'total_amount', 'amount_paid', 'balance', 'payment_status')
    list_filter = ('payment_status', 'payment_mode', 'payment_date')
    search_fields = ('patient__name', 'receipt_number')
    readonly_fields = ('receipt_number',)
