from rest_framework import serializers
from spinalcure.utils import B64UUIDField
from .models import Patient, Session

class SessionSerializer(serializers.ModelSerializer):
    id = B64UUIDField(read_only=True)
    consulted_by_name = serializers.CharField(source='consulted_by.name', read_only=True)
    
    class Meta:
        model = Session
        fields = '__all__'
        read_only_fields = ('session_number',)

class PatientSerializer(serializers.ModelSerializer):
    id = B64UUIDField(read_only=True)
    completed_sittings = serializers.IntegerField(read_only=True)
    remaining_sittings = serializers.IntegerField(read_only=True)
    progress_percentage = serializers.IntegerField(read_only=True)
    age = serializers.IntegerField(read_only=True)
    
    class Meta:
        model = Patient
        fields = '__all__'

class PatientDetailSerializer(PatientSerializer):
    sessions = SessionSerializer(many=True, read_only=True)
