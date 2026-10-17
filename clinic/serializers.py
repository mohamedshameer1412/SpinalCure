from rest_framework import serializers
from spinalcure.utils import B64UUIDField
from .models import ClinicProfile, Practitioner

class ClinicProfileSerializer(serializers.ModelSerializer):
    id = B64UUIDField(read_only=True)
    class Meta:
        model = ClinicProfile
        fields = '__all__'

class PractitionerSerializer(serializers.ModelSerializer):
    id = B64UUIDField(read_only=True)
    class Meta:
        model = Practitioner
        fields = '__all__'
