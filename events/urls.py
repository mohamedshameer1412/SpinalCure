from . import views
"""
Events URLs.
Note: Events API viewset routing is handled in spinalcure/urls.py
"""
from django.urls import path
from .views import (event_list_view, event_create_view, event_edit_view, event_delete_view, toggle_event_publish,
                    event_registrations_view, event_feedback_admin_view,
                    export_events_excel, export_events_csv, export_events_pdf, 
                    export_events_copy, export_events_print,
                    export_event_registrations_excel, export_event_registrations_csv,
                    export_event_registrations_pdf, export_event_registrations_copy,
                    export_event_registrations_print,
                    toggle_event_feedback, toggle_feedback_publish)

urlpatterns = [
    path('', event_list_view, name='event_list'),
    path('export/excel/', export_events_excel, name='export_events_excel'),
    path('export/csv/', export_events_csv, name='export_events_csv'),
    path('export/pdf/', export_events_pdf, name='export_events_pdf'),
    path('export/copy/', export_events_copy, name='export_events_copy'),
    path('export/print/', export_events_print, name='export_events_print'),
    path('<b64uuid:pk>/export/excel/', export_event_registrations_excel, name='export_event_registrations_excel'),
    path('<b64uuid:pk>/export/csv/', export_event_registrations_csv, name='export_event_registrations_csv'),
    path('<b64uuid:pk>/export/pdf/', export_event_registrations_pdf, name='export_event_registrations_pdf'),
    path('<b64uuid:pk>/export/copy/', export_event_registrations_copy, name='export_event_registrations_copy'),
    path('<b64uuid:pk>/export/print/', export_event_registrations_print, name='export_event_registrations_print'),
    path('create/', event_create_view, name='event_create'),
    path('<b64uuid:pk>/edit/', event_edit_view, name='event_edit'),
    path('<b64uuid:pk>/delete/', event_delete_view, name='event_delete'),
    path('<b64uuid:pk>/toggle-publish/', toggle_event_publish, name='toggle_event_publish'),
    # Admin - Registrations & Feedback
    path('<b64uuid:pk>/registrations/', event_registrations_view, name='event_registrations'),
    path('<b64uuid:pk>/lifecycle/', views.event_lifecycle_view, name='event_lifecycle'),
    path('registrations/<b64uuid:pk>/update/', views.registration_update_view, name='event_registration_update'),
    path('<b64uuid:pk>/feedback/', event_feedback_admin_view, name='event_feedback_admin'),
    path('<b64uuid:pk>/toggle-feedback/', toggle_event_feedback, name='toggle_event_feedback'),
    path('feedback/<b64uuid:feedback_pk>/toggle-publish/', toggle_feedback_publish, name='toggle_feedback_publish'),
]
