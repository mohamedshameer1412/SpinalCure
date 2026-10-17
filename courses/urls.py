from django.urls import path
from . import views

urlpatterns = [
    path('', views.course_list_view, name='course_list'),
    path('export/excel/', views.export_courses_excel, name='export_courses_excel'),
    path('export/csv/', views.export_courses_csv, name='export_courses_csv'),
    path('export/pdf/', views.export_courses_pdf, name='export_courses_pdf'),
    path('export/copy/', views.export_courses_copy, name='export_courses_copy'),
    path('export/print/', views.export_courses_print, name='export_courses_print'),

    path('batches/<b64uuid:pk>/export/excel/', views.export_batch_registrations_excel, name='export_batch_registrations_excel'),
    path('batches/<b64uuid:pk>/export/csv/', views.export_batch_registrations_csv, name='export_batch_registrations_csv'),
    path('batches/<b64uuid:pk>/export/pdf/', views.export_batch_registrations_pdf, name='export_batch_registrations_pdf'),
    path('batches/<b64uuid:pk>/export/copy/', views.export_batch_registrations_copy, name='export_batch_registrations_copy'),
    path('batches/<b64uuid:pk>/export/print/', views.export_batch_registrations_print, name='export_batch_registrations_print'),
    path('create/', views.course_create_view, name='course_create'),
    path('<b64uuid:pk>/edit/', views.course_edit_view, name='course_edit'),
    path('<b64uuid:pk>/delete/', views.course_delete_view, name='course_delete'),
    path('<b64uuid:pk>/toggle-publish/', views.toggle_course_publish, name='toggle_course_publish'),
    # Batches
    path('<b64uuid:course_pk>/batches/', views.batch_list_view, name='batch_list'),
    path('<b64uuid:course_pk>/batches/create/', views.batch_create_view, name='batch_create'),
    path('batches/<b64uuid:pk>/edit/', views.batch_edit_view, name='batch_edit'),
    path('batches/<b64uuid:pk>/delete/', views.batch_delete_view, name='batch_delete'),
    # Registrations & Feedback Admin
    path('batches/<b64uuid:pk>/registrations/', views.batch_registrations_view, name='batch_registrations'),
    path('batches/<b64uuid:pk>/feedback/', views.batch_feedback_admin_view, name='batch_feedback_admin'),
    path('batches/<b64uuid:pk>/toggle-feedback/', views.toggle_batch_feedback, name='toggle_batch_feedback'),
    path('feedback/<b64uuid:feedback_pk>/toggle-publish/', views.toggle_course_feedback_publish, name='toggle_course_feedback_publish'),
]
