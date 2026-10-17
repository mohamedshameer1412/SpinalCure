from django.contrib import admin
from .models import Appointment, DoctorAvailability

@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ('patient', 'practitioner', 'appointment_date', 'appointment_time', 'status')
    list_filter = ('status', 'appointment_date', 'practitioner')
    search_fields = ('patient__name',)

@admin.register(DoctorAvailability)
class DoctorAvailabilityAdmin(admin.ModelAdmin):
    list_display = ('practitioner', 'day_of_week', 'start_time', 'end_time', 'is_available')
    list_filter = ('day_of_week', 'is_available', 'practitioner')
