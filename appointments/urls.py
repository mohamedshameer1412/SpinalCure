from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (appointment_calendar_view, 
                     appointment_list_view, export_appointments_excel, export_appointments_csv,
                     export_appointments_pdf, export_appointments_copy, export_appointments_print,
                     appointment_delete_view, appointment_check_collision, get_available_slots)
from .public_views import manage, manage_slots
from . import schedule_views as sv
from .api_views import AppointmentViewSet, DoctorAvailabilityViewSet

router = DefaultRouter()
router.register(r'bookings', AppointmentViewSet)
router.register(r'availability', DoctorAvailabilityViewSet)

urlpatterns = [
    path('', appointment_calendar_view, name='appointment_calendar'),
    path('list/', appointment_list_view, name='appointment_list'),
    path('<uuid:pk>/delete/', appointment_delete_view, name='appointment_delete'),
    path('api/check-collision/', appointment_check_collision, name='appointment_check_collision'),
    path('api/available-slots/', get_available_slots, name='api_available_slots'),
    path('export/excel/', export_appointments_excel, name='export_appointments_excel'),
    path('export/csv/', export_appointments_csv, name='export_appointments_csv'),
    path('export/pdf/', export_appointments_pdf, name='export_appointments_pdf'),
    path('export/copy/', export_appointments_copy, name='export_appointments_copy'),
    path('export/print/', export_appointments_print, name='export_appointments_print'),
    path('availability/', sv.availability, name='doctor_availability'),
    path('availability/<str:practitioner_id>/shift/', sv.shift_save, name='shift_save'),
    path('availability/<str:practitioner_id>/shift/<uuid:pk>/delete/', sv.shift_delete, name='shift_delete'),
    path('availability/<str:practitioner_id>/time-off/', sv.timeoff_save, name='timeoff_save'),
    path('availability/time-off/<uuid:pk>/delete/', sv.timeoff_delete, name='timeoff_delete'),
    path('availability/settings/', sv.booking_settings_save, name='booking_settings_save'),
    path('manage/<str:token>/', manage, name='appointment_manage'),
    path('manage/<str:token>/slots/', manage_slots, name='appointment_manage_slots'),
    path('api/', include(router.urls)),
]
