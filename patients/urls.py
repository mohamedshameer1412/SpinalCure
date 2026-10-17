from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (PatientViewSet, SessionViewSet, patient_list_view,
                    patient_detail_view, patient_print_card_view,
                    patient_create_view, patient_edit_view, patient_delete_view,
                    session_create_view, session_edit_view, session_delete_view,
                    session_request_pin_view, session_verify_pin_view,
                    export_patients_excel, export_patients_csv,
                    export_patients_pdf, export_patients_copy, export_patients_print,
                    reviews_list_view, review_create_view,
                    review_toggle_publish, review_delete_view,
                    export_reviews_excel, export_reviews_csv,
                    export_reviews_pdf, export_reviews_copy, export_reviews_print,
                    session_pdf_view, patient_login_view, patient_verify_otp_view,
                    patient_dashboard_view, patient_logout_view,
                    treatment_plan_create_view, treatment_plan_edit_view,
                    treatment_plan_delete_view)

router = DefaultRouter()
router.register(r'patients', PatientViewSet, basename='api-patient')
router.register(r'sessions', SessionViewSet, basename='api-session')

urlpatterns = [
    # Web UI
    path('', patient_list_view, name='patient-list'),
    path('export/excel/', export_patients_excel, name='export_patients_excel'),
    path('export/csv/', export_patients_csv, name='export_patients_csv'),
    path('export/pdf/', export_patients_pdf, name='export_patients_pdf'),
    path('export/copy/', export_patients_copy, name='export_patients_copy'),
    path('export/print/', export_patients_print, name='export_patients_print'),
    path('create/', patient_create_view, name='patient-create'),
    path('<b64uuid:pk>/', patient_detail_view, name='patient-detail'),
    path('<b64uuid:pk>/edit/', patient_edit_view, name='patient-edit'),
    path('<b64uuid:pk>/delete/', patient_delete_view, name='patient-delete'),
    path('<b64uuid:pk>/print/', patient_print_card_view, name='patient_print_card'),
    
    # Treatment Plans
    path('<b64uuid:patient_pk>/plans/create/', treatment_plan_create_view, name='treatment-plan-create'),
    path('<b64uuid:patient_pk>/plans/<uuid:plan_pk>/edit/', treatment_plan_edit_view, name='treatment-plan-edit'),
    path('<b64uuid:patient_pk>/plans/<uuid:plan_pk>/delete/', treatment_plan_delete_view, name='treatment-plan-delete'),
    
    # Sessions
    path('<b64uuid:patient_pk>/sessions/create/', session_create_view, name='session-create'),
    path('<b64uuid:patient_pk>/sessions/<b64uuid:session_pk>/edit/', session_edit_view, name='session-edit'),
    path('<b64uuid:patient_pk>/sessions/<b64uuid:session_pk>/delete/', session_delete_view, name='session-delete'),
    path('sessions/<b64uuid:session_pk>/pdf/', session_pdf_view, name='session-pdf'),
    
    # Security PIN endpoints (AJAX)
    path('sessions/request-pin/', session_request_pin_view, name='session-request-pin'),
    path('sessions/verify-pin/', session_verify_pin_view, name='session-verify-pin'),
    
    # Reviews
    path('reviews/', reviews_list_view, name='patient-reviews'),
    path('reviews/export/excel/', export_reviews_excel, name='export-reviews-excel'),
    path('reviews/export/csv/', export_reviews_csv, name='export-reviews-csv'),
    path('reviews/export/pdf/', export_reviews_pdf, name='export_reviews_pdf'),
    path('reviews/export/copy/', export_reviews_copy, name='export_reviews_copy'),
    path('reviews/export/print/', export_reviews_print, name='export_reviews_print'),
    path('reviews/create/', review_create_view, name='review-create'),
    path('reviews/<b64uuid:pk>/toggle/', review_toggle_publish, name='review-toggle'),
    path('reviews/<b64uuid:pk>/delete/', review_delete_view, name='review-delete'),
    
    # API
    path('api/', include(router.urls)),
    
    # ── Patient Portal (Self-Service) ───────────────────────────────────────
    path('portal/login/', patient_login_view, name='portal_login'),
    path('portal/verify/', patient_verify_otp_view, name='portal_verify'),
    path('portal/dashboard/', patient_dashboard_view, name='portal_dashboard'),
    path('portal/logout/', patient_logout_view, name='portal_logout'),
]
