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
        
    def get_patient_name(self, obj):
        return obj.patient.name if obj.patient else (obj.guest_name or 'Guest')
        
    def get_patient_phone(self, obj):
        return obj.patient.phone if obj.patient else (obj.guest_phone or '')
        
    def get_patient_id_display(self, obj):
        return self.get_patient_phone(obj)

