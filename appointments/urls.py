from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (appointment_calendar_view, doctor_availability_view, 
                     appointment_list_view, export_appointments_excel, export_appointments_csv,
                     export_appointments_pdf, export_appointments_copy, export_appointments_print,
                     appointment_delete_view, get_available_slots)
from .api_views import AppointmentViewSet, DoctorAvailabilityViewSet

router = DefaultRouter()
router.register(r'bookings', AppointmentViewSet)
router.register(r'availability', DoctorAvailabilityViewSet)

urlpatterns = [
    path('', appointment_calendar_view, name='appointment_calendar'),
    path('list/', appointment_list_view, name='appointment_list'),
    path('<b64uuid:pk>/delete/', appointment_delete_view, name='appointment_delete'),
    path('api/available-slots/', get_available_slots, name='api_available_slots'),
    path('export/excel/', export_appointments_excel, name='export_appointments_excel'),
    path('export/csv/', export_appointments_csv, name='export_appointments_csv'),
    path('export/pdf/', export_appointments_pdf, name='export_appointments_pdf'),
    path('export/copy/', export_appointments_copy, name='export_appointments_copy'),
    path('export/print/', export_appointments_print, name='export_appointments_print'),
    path('availability/', doctor_availability_view, name='doctor_availability'),
    path('api/', include(router.urls)),
]
