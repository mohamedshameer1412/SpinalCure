from rest_framework import serializers

from spinalcure.utils import B64UUIDField

from .models import Event

PUBLIC_FIELDS = ['id', 'title', 'event_type', 'description', 'presenter', 'image', 'date', 'start_time', 'end_time',
                 'timezone', 'language', 'venue', 'is_online', 'max_participants', 'registration_required',
                 'registration_deadline', 'fees', 'status', 'phase', 'seats_left', 'is_full']


class EventPublicSerializer(serializers.ModelSerializer):
    """What anonymous visitors may see. Meeting link, passcode and instructions are never included."""
    id = B64UUIDField(read_only=True)
    phase = serializers.CharField(read_only=True)
    seats_left = serializers.IntegerField(read_only=True)
    is_full = serializers.BooleanField(read_only=True)

    class Meta:
        model = Event
        fields = PUBLIC_FIELDS
        read_only_fields = PUBLIC_FIELDS


class EventSerializer(serializers.ModelSerializer):
    """Staff view, including private joining details."""
    id = B64UUIDField(read_only=True)
    phase = serializers.CharField(read_only=True)
    is_upcoming = serializers.BooleanField(read_only=True)
    confirmed_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Event
        fields = '__all__'
        read_only_fields = ('status', 'is_published', 'cancel_reason', 'organizer')
