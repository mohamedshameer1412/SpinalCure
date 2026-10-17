from django.contrib import admin
from .models import Patient, Session

class SessionInline(admin.TabularInline):
    model = Session
    extra = 0
    readonly_fields = ('session_number', 'created_at')

@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone', 'registered_date', 'completed_sittings', 'total_sittings')
    search_fields = ('name', 'phone')
    inlines = [SessionInline]

@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ('patient', 'session_number', 'session_date', 'consulted_by')
    list_filter = ('session_date', 'consulted_by')
    search_fields = ('patient__name', 'acupoints_used')
