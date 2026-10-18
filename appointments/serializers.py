from rest_framework import serializers
from spinalcure.utils import B64UUIDField
from appointments.models import Appointment, DoctorAvailability

class DoctorAvailabilitySerializer(serializers.ModelSerializer):
    id = B64UUIDField(read_only=True)
    practitioner_name = serializers.CharField(source='practitioner.name', read_only=True)
    
    class Meta:
        model = DoctorAvailability
        fields = '__all__'

class AppointmentSerializer(serializers.ModelSerializer):
    id = B64UUIDField(read_only=True)
    patient_name = serializers.SerializerMethodField()
    patient_id_display = serializers.SerializerMethodField()
    patient_phone = serializers.SerializerMethodField()
    practitioner_name = serializers.CharField(source='practitioner.name', read_only=True)
    patient_b64 = B64UUIDField(source='patient.id', read_only=True)
    
    class Meta:
        model = Appointment
        fields = '__all__'
        
    def validate(self, attrs):
        inst = self.instance
        status = attrs.get('status')
        if inst is None:
            if status not in (None, 'scheduled', 'confirmed'):
                raise serializers.ValidationError({'detail': 'New appointments must be scheduled or confirmed.'})
            if not attrs.get('patient') and not attrs.get('guest_name'):
                raise serializers.ValidationError({'detail': 'Choose a patient or enter a guest name.'})
        elif status and status != inst.status and status not in Appointment.TRANSITIONS.get(inst.status, set()):
            raise serializers.ValidationError(
                {'detail': f'Cannot change status from {inst.get_status_display()} to {dict(Appointment.STATUS_CHOICES).get(status, status)}.'})
        elif inst.status not in ('scheduled', 'confirmed') and any(
                f in attrs for f in ('appointment_date', 'appointment_time', 'practitioner', 'duration_minutes')):
            raise serializers.ValidationError({'detail': 'Closed appointments cannot be moved.'})
        return attrs

    def get_patient_name(self, obj):
        return obj.patient.name if obj.patient else (obj.guest_name or 'Guest')
        
    def get_patient_phone(self, obj):
        return obj.patient.phone if obj.patient else (obj.guest_phone or '')
        
    def get_patient_id_display(self, obj):
        return self.get_patient_phone(obj)

