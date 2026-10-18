from django.contrib import admin

from .models import Notification, NotificationDelivery, NotificationPreference


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'event_type', 'title', 'user', 'persistent', 'read_at')
    list_filter = ('event_type', 'persistent')
    readonly_fields = [f.name for f in Notification._meta.fields]


@admin.register(NotificationDelivery)
class DeliveryAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'channel', 'status', 'attempts', 'notification')
    list_filter = ('channel', 'status')


admin.site.register(NotificationPreference)
