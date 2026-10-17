from rest_framework import serializers
from spinalcure.utils import B64UUIDField
from .models import Event

class EventSerializer(serializers.ModelSerializer):
    id = B64UUIDField(read_only=True)
    is_upcoming = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = Event
        fields = '__all__'
