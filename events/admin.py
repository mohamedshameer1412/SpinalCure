from django.contrib import admin
from .models import Event

@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ('title', 'event_type', 'date', 'start_time', 'is_published')
    list_filter = ('event_type', 'is_published', 'date')
    search_fields = ('title',)
