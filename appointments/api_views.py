from django.db import transaction
from rest_framework import viewsets, filters
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.permissions import IsAuthenticated
from .models import Appointment, DoctorAvailability
from .serializers import AppointmentSerializer, DoctorAvailabilitySerializer
from .scheduling import booking_lock, check_bookable, BookingError
from spinalcure.utils import log_action, decode_b64uuid
from spinalcure.permissions import IsDoctor
import logging
from spinalcure.permissions import ReadWritePerm

logger = logging.getLogger(__name__)


class AppointmentViewSet(viewsets.ModelViewSet):
    """
    Appointments API used by the staff calendar. Every write is re-validated by
    appointments.scheduling under a per-practitioner-day lock.
    Calendar range: ?start=YYYY-MM-DD&end=YYYY-MM-DD (end exclusive).
    """
    queryset = Appointment.objects.all().order_by('-appointment_date', '-appointment_time')
    serializer_class = AppointmentSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['patient', 'practitioner', 'status', 'appointment_date']
    search_fields = ['notes', 'reason']  # patient names are encrypted; use Patient.search for those
    ordering_fields = ['appointment_date', 'created_at']
    permission_classes = [ReadWritePerm('appointments_view', 'appointments_manage', 'appointments_delete')]
    pagination_class = None

    def get_queryset(self):
        qs = Appointment.objects.select_related('patient', 'practitioner')
        start, end = self.request.query_params.get('start'), self.request.query_params.get('end')
        if start:
            qs = qs.filter(appointment_date__gte=start[:10])
        if end:
            qs = qs.filter(appointment_date__lt=end[:10])
        return qs

    def get_object(self):
        pk = self.kwargs.get(self.lookup_field, '')
        if len(pk) == 22:  # calendar sends base64 ids
            self.kwargs[self.lookup_field] = decode_b64uuid(pk) or pk
        return super().get_object()

    def _save_checked(self, serializer, instance=None):
        data = serializer.validated_data
        get = lambda f: data.get(f, getattr(instance, f, None))  # noqa: E731
        practitioner, day, start = get('practitioner'), get('appointment_date'), get('appointment_time')
        duration = get('duration_minutes') or 30
        timing_changed = instance is None or any(
            f in data and data[f] != getattr(instance, f) for f in ('practitioner', 'appointment_date', 'appointment_time', 'duration_minutes'))
        if not timing_changed:
            return serializer.save()
        try:
            with booking_lock(practitioner.pk if practitioner else None, day), transaction.atomic():
                error = check_bookable(practitioner, day, start, duration, get('appointment_type') or 'physical',
                                       exclude_id=instance.pk if instance else None)
                if error:
                    raise ValidationError({'detail': error})
                return serializer.save()
        except BookingError as e:
            raise ValidationError({'detail': str(e)})

    def perform_create(self, serializer):
        appointment = self._save_checked(serializer)
        log_action(self.request, 'create', 'Appointment', str(appointment), object_id=appointment.pk)
        from clinic.email_utils import send_booking_confirmation_email
        try:
            send_booking_confirmation_email(appointment, self.request)
        except Exception as e:
            logger.error(f"Error sending appointment email: {str(e)}")

    def perform_update(self, serializer):
        old = serializer.instance
        before = {'status': old.status, 'date': str(old.appointment_date), 'time': str(old.appointment_time)}
        appointment = self._save_checked(serializer, instance=old)
        after = {'status': appointment.status, 'date': str(appointment.appointment_date), 'time': str(appointment.appointment_time)}
        changes = {k: {'old': before[k], 'new': after[k]} for k in before if before[k] != after[k]}
        if changes:
            log_action(self.request, 'update', 'Appointment', str(appointment), object_id=appointment.pk, changes=changes)

    @action(detail=True, methods=['post'])
    def reschedule(self, request, pk=None):
        """POST {date, time[, practitioner]}: move an active appointment to a new, free slot."""
        appointment = self.get_object()
        if appointment.status not in ('scheduled', 'confirmed'):
            return Response({'detail': 'Only scheduled or confirmed appointments can be rescheduled.'}, status=400)
        payload = {'appointment_date': request.data.get('date'), 'appointment_time': request.data.get('time')}
        if 'practitioner' in request.data:
            payload['practitioner'] = request.data['practitioner'] or None
        serializer = self.get_serializer(appointment, data=payload, partial=True)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(self.get_serializer(appointment).data)


class DoctorAvailabilityViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing doctor availability schedules.
    Only doctors and admins can manage their availability.
    """
    queryset = DoctorAvailability.objects.select_related('practitioner').order_by('day_of_week', 'start_time')
    serializer_class = DoctorAvailabilitySerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['practitioner', 'day_of_week', 'is_available']
    permission_classes = [IsAuthenticated, IsDoctor]

    def get_queryset(self):
        """Doctors only see their own availability."""
        user = self.request.user
        if user.role == 'superadmin' or user.is_superuser:
            return DoctorAvailability.objects.all()
        return DoctorAvailability.objects.filter(practitioner__email=user.email)

