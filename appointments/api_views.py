from datetime import datetime

from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.permissions import IsAuthenticated
from .models import Appointment, DoctorAvailability
from .serializers import AppointmentSerializer, DoctorAvailabilitySerializer
from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
from clinic.models import Practitioner
from spinalcure.permissions import IsSuperAdmin
from spinalcure.rbac import capability_rw_permission

from . import scheduling as sch
import logging

logger = logging.getLogger(__name__)


class AppointmentViewSet(viewsets.ModelViewSet):
    """
    Staff appointment API. Every write goes through appointments.scheduling so the same availability,
    conflict and state-machine rules apply as for the public form; the browser's slot picker is advisory.
    """
    queryset = Appointment.objects.all().order_by('-appointment_date', '-appointment_time')
    serializer_class = AppointmentSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['patient', 'practitioner', 'status', 'appointment_date']
    ordering_fields = ['appointment_date', 'created_at']
    permission_classes = [IsAuthenticated, capability_rw_permission('appointments.manage', 'appointments.manage')]
    pagination_class = None
    http_method_names = ['get', 'post', 'patch', 'put', 'delete', 'head', 'options']

    def get_queryset(self):
        qs = Appointment.objects.select_related('patient', 'practitioner')
        start, end = self.request.query_params.get('start'), self.request.query_params.get('end')
        if start:
            qs = qs.filter(appointment_date__gte=str(start)[:10])
        if end:
            qs = qs.filter(appointment_date__lte=str(end)[:10])
        return qs

    def get_permissions(self):
        if self.action == 'destroy':        # deletion destroys history; cancel instead (PIN-protected UI exists)
            return [IsAuthenticated(), IsSuperAdmin()]
        return super().get_permissions()

    @staticmethod
    def _error(exc):
        return Response({'detail': exc.message, 'code': exc.code},
                        status=status.HTTP_409_CONFLICT if exc.code in ('conflict', 'unavailable')
                        else status.HTTP_400_BAD_REQUEST)

    def create(self, request, *args, **kwargs):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        if not d.get('patient'):
            return Response({'detail': 'A patient is required.', 'code': 'invalid_contact'}, status=400)
        try:
            appt = sch.book(
                practitioner=d.get('practitioner'), day=d['appointment_date'], start_time=d['appointment_time'],
                appointment_type=d.get('appointment_type', 'physical'), duration=d.get('duration_minutes'),
                patient=d['patient'], reason=d.get('reason', ''), source='staff', actor=request.user,
                request_key=(request.headers.get('Idempotency-Key') or '')[:64] or None,
                ignore_hours=bool(request.data.get('allow_outside_hours')),
                ignore_notice=bool(request.data.get('allow_outside_hours')))
        except sch.SchedulingError as exc:
            return self._error(exc)
        log_api_action(request, 'create', appt)
        return Response(self.get_serializer(appt).data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        appt = self.get_object()
        data = request.data
        try:
            moved = any(k in data for k in ('appointment_date', 'appointment_time', 'practitioner'))
            if moved:
                new_day = datetime.strptime(str(data.get('appointment_date', appt.appointment_date))[:10], '%Y-%m-%d').date()
                raw_t = str(data.get('appointment_time', appt.appointment_time))[:5]
                new_time = datetime.strptime(raw_t, '%H:%M').time()
                pr = appt.practitioner
                if data.get('practitioner'):
                    pr = Practitioner.objects.filter(pk=data['practitioner'], is_active=True).first()
                    if pr is None:
                        return Response({'detail': 'Unknown practitioner.', 'code': 'unknown_practitioner'}, status=400)
                if (new_day, new_time, getattr(pr, 'pk', None)) != (
                        appt.appointment_date, appt.appointment_time.replace(second=0, microsecond=0),
                        getattr(appt.practitioner, 'pk', None)):
                    appt = sch.reschedule(appt, day=new_day, start_time=new_time, practitioner=pr, actor=request.user,
                                          ignore_hours=bool(data.get('allow_outside_hours')),
                                          ignore_notice=bool(data.get('allow_outside_hours')))
            new_status = data.get('status')
            if new_status and new_status != appt.status:
                actions = {'confirmed': sch.confirm, 'completed': sch.complete, 'no_show': sch.mark_no_show}
                if new_status == 'cancelled':
                    appt = sch.cancel(appt, actor=request.user, reason=str(data.get('cancel_reason', '')))
                elif new_status in actions:
                    appt = actions[new_status](appt, request.user)
                else:
                    return Response({'detail': 'Invalid status change.', 'code': 'invalid_transition'}, status=400)
            for field in ('reason', 'notes'):
                if field in data:
                    setattr(appt, field, str(data[field])[:300 if field == 'reason' else 5000])
            appt.save()
        except ValueError:
            return Response({'detail': 'Invalid date or time.', 'code': 'invalid_time'}, status=400)
        except sch.SchedulingError as exc:
            return self._error(exc)
        log_api_action(request, 'update', appt)
        return Response(self.get_serializer(appt).data)

    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        try:
            appt = sch.cancel(self.get_object(), actor=request.user, reason=str(request.data.get('reason', '')))
        except sch.SchedulingError as exc:
            return self._error(exc)
        return Response(self.get_serializer(appt).data)


def log_api_action(request, verb, appt):
    try:
        from spinalcure.utils import log_action
        log_action(request, verb, 'Appointment', f'{appt.display_name} {appt.appointment_date} {appt.appointment_time}',
                   object_id=appt.pk)
    except Exception:
        logger.exception('audit log failed')


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

