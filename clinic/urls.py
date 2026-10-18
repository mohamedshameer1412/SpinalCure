from . import views
from django.urls import path
from .views import (clinic_portfolio_view, practitioner_detail_view,
                    submit_review_ajax, book_appointment_ajax, clinic_about_page_view,
                    event_detail_view, register_for_event_ajax, submit_event_feedback_ajax,
                    verify_event_registration_ajax, course_detail_view,
                    register_for_course_ajax, verify_course_registration_ajax,
                    submit_course_feedback_ajax, global_search_ajax)
from .admin_views import (clinic_setup_view, practitioners_list,
                          practitioner_create, practitioner_edit, practitioner_delete,
                          testimonials_list, testimonial_create, testimonial_edit,
                          testimonial_delete, testimonial_toggle_publish, activity_log_view, revert_audit_log_view)
from .blog_views import blog_list_view, blog_detail_view
from .blog_admin_views import (admin_blog_list, admin_blog_create, admin_blog_edit,
                                admin_blog_delete, admin_tag_list)

urlpatterns = [
    # ── API / Search ──────────────────────────────────────────────────────────
    path('api/global-search/', global_search_ajax, name='global_search'),

    # ── Public Views ──────────────────────────────────────────────────
    path('portfolio/', clinic_portfolio_view, name='clinic_portfolio'),
    path('about/', clinic_about_page_view, name='clinic_about_page'),
    path('practitioners/<b64uuid:pk>/', practitioner_detail_view, name='practitioner_detail'),
    path('ajax/submit-review/', submit_review_ajax, name='submit_review_ajax'),
    path('ajax/book-appointment/', book_appointment_ajax, name='book_appointment_ajax'),

    # ── Public Event Detail ───────────────────────────────────────────
    path('events/', views.public_event_list_view, name='public_event_list'),
    path('events/<b64uuid:pk>/', event_detail_view, name='event_detail'),
    path('events/<b64uuid:pk>/calendar.ics', views.event_ics_view, name='event_ics'),
    path('events/registration/<str:token>/', views.event_registration_manage_view, name='event_registration_manage'),
    path('events/registration/<str:token>/join/', views.event_join_view, name='event_join'),
    path('events/<b64uuid:pk>/register/', register_for_event_ajax, name='event_register_ajax'),
    path('events/<b64uuid:pk>/verify-registration/', verify_event_registration_ajax, name='event_verify_registration_ajax'),
    path('events/<b64uuid:pk>/feedback/', submit_event_feedback_ajax, name='event_feedback_ajax'),

    # ── Public Course Detail ──────────────────────────────────────────
    path('courses/<b64uuid:pk>/', course_detail_view, name='course_detail'),
    path('courses/<b64uuid:pk>/register/', register_for_course_ajax, name='course_register_ajax'),
    path('courses/<b64uuid:pk>/verify-registration/', verify_course_registration_ajax, name='course_verify_registration_ajax'),
    path('courses/<b64uuid:pk>/feedback/', submit_course_feedback_ajax, name='course_feedback_ajax'),

    # ── Public Blog ───────────────────────────────────────────────────
    path('blog/', blog_list_view, name='blog_list'),
    path('blog/<slug:slug>/', blog_detail_view, name='blog_detail'),

    # ── Admin (Dashboard) Views ───────────────────────────────────────
    path('admin/setup/', clinic_setup_view, name='admin_clinic_setup'),
    path('admin/practitioners/', practitioners_list, name='admin_practitioners'),
    path('admin/practitioners/create/', practitioner_create, name='admin_practitioner_create'),
    path('admin/practitioners/<b64uuid:pk>/edit/', practitioner_edit, name='admin_practitioner_edit'),
    path('admin/practitioners/<b64uuid:pk>/delete/', practitioner_delete, name='admin_practitioner_delete'),

    # ── Admin Blog ────────────────────────────────────────────────────
    path('admin/blog/', admin_blog_list, name='admin_blog_list'),
    path('admin/blog/create/', admin_blog_create, name='admin_blog_create'),
    path('admin/blog/<uuid:pk>/edit/', admin_blog_edit, name='admin_blog_edit'),
    path('admin/blog/<uuid:pk>/delete/', admin_blog_delete, name='admin_blog_delete'),
    path('admin/blog/tags/', admin_tag_list, name='admin_blog_tags'),

    # ── Admin Testimonials ───────────────────────────────────────────────
    path('admin/testimonials/', testimonials_list, name='admin_testimonials'),
    path('admin/testimonials/create/', testimonial_create, name='admin_testimonial_create'),
    path('admin/testimonials/<uuid:pk>/edit/', testimonial_edit, name='admin_testimonial_edit'),
    path('admin/testimonials/<uuid:pk>/delete/', testimonial_delete, name='admin_testimonial_delete'),
    path('admin/testimonials/<uuid:pk>/toggle/', testimonial_toggle_publish, name='admin_testimonial_toggle'),

    # ── Admin Activity Log ──────────────────────────────────────────
    path('admin/activity-log/', activity_log_view, name='admin_activity_log'),
    path('admin/activity-log/<uuid:pk>/revert/', revert_audit_log_view, name='admin_revert_log'),
]
