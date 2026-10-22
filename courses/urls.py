from django.urls import path
from . import student_views, views

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
    path('students/', student_views.student_list, name='student_list'),
    path('students/<b64uuid:pk>/', student_views.student_detail, name='student_detail'),
    path('students/<b64uuid:pk>/edit/', student_views.student_edit, name='student_edit'),
    path('students/<b64uuid:pk>/note/', student_views.student_note_add, name='student_note_add'),
    path('students/<b64uuid:pk>/note/<uuid:note_pk>/done/', student_views.student_note_done, name='student_note_done'),
    path('students/<b64uuid:pk>/send-link/', student_views.student_send_link, name='student_send_link'),
    path('students/<b64uuid:pk>/card/<str:side>.png', student_views.student_card_png, name='student_card_png'),
    path('students/<b64uuid:pk>/card.pdf', student_views.student_card_pdf, name='student_card_pdf'),
    path('batches/<b64uuid:pk>/request-feedback/', student_views.batch_request_feedback, name='batch_request_feedback'),
    path('batches/<b64uuid:pk>/remind-profiles/', student_views.batch_remind_profiles, name='batch_remind_profiles'),
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
    path('batches/<b64uuid:pk>/registrations/<uuid:reg_pk>/cancel/', views.batch_registration_cancel, name='batch_registration_cancel'),
    path('batches/<b64uuid:pk>/promote/', views.batch_promote_waitlist, name='batch_promote_waitlist'),
    path('batches/<b64uuid:pk>/feedback/', views.batch_feedback_admin_view, name='batch_feedback_admin'),
    path('batches/<b64uuid:pk>/toggle-feedback/', views.toggle_batch_feedback, name='toggle_batch_feedback'),
    path('feedback/<b64uuid:feedback_pk>/toggle-publish/', views.toggle_course_feedback_publish, name='toggle_course_feedback_publish'),
]
