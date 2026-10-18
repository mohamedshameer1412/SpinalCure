from rest_framework import viewsets, filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.permissions import IsAuthenticated
from .models import Appointment, DoctorAvailability
from .serializers import AppointmentSerializer, DoctorAvailabilitySerializer
from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
from spinalcure.rbac import capability_rw_permission
import logging

logger = logging.getLogger(__name__)


class AppointmentViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing appointments.
    Doctors can view all, receptionists can create/modify, patients see their own.
    """
    queryset = Appointment.objects.all().order_by('-appointment_date', '-appointment_time')
    serializer_class = AppointmentSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['patient', 'practitioner', 'status', 'appointment_date']
    search_fields = ['patient__name', 'notes']
    ordering_fields = ['appointment_date', 'created_at']
    permission_classes = [IsAuthenticated, capability_rw_permission('appointments.manage', 'appointments.manage')]
    pagination_class = None

    def get_queryset(self):
        """Return all appointments; specific filtering is handled by the frontend."""
        return Appointment.objects.select_related('patient', 'practitioner').all()

    def perform_create(self, serializer):
        """Send confirmation email when appointment is created."""
        appointment = serializer.save()
        
        from clinic.email_utils import send_booking_confirmation_email
        try:
            send_booking_confirmation_email(appointment, self.request)
        except Exception as e:
            logger.error(f"Error sending appointment email: {str(e)}")


class DoctorAvailabilityViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing doctor availability schedules.
    Only doctors and admins can manage their availability.
    """
    queryset = DoctorAvailability.objects.select_related('practitioner').order_by('day_of_week', 'start_time')
    serializer_class = DoctorAvailabilitySerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['practitioner', 'day_of_week', 'is_available']
    permission_classes = [IsAuthenticated, capability_rw_permission('appointments.manage', 'schedule.manage')]

    def get_queryset(self):
        """Doctors only see their own availability; management roles see all."""
        user = self.request.user
        if user.role != 'doctor':
            return DoctorAvailability.objects.all()
        return DoctorAvailability.objects.filter(practitioner__email=user.email)

