from django.urls import path
from django.views.generic import RedirectView
from events import public_views as pev
from courses import public_views as pcv
from courses import student_views
from .views import (clinic_portfolio_view, practitioner_detail_view,
                    submit_review_ajax, review_withdraw, book_appointment_ajax, clinic_about_page_view,
                    course_detail_view,
                    global_search_ajax)
from .admin_views import (clinic_setup_view, practitioners_list,
                          practitioner_create, practitioner_edit, practitioner_delete,
                          testimonials_list, testimonial_create, testimonial_edit,
                          testimonial_delete, testimonial_toggle_publish, testimonial_moderate, activity_log_view, revert_audit_log_view)
from .testimonial_views import (testimonials_page, admin_videos, admin_videos_sync, admin_video_edit, admin_video_toggle, admin_video_delete, admin_video_problem,
                                admin_problems, admin_problem_delete)
from .translation_views import translations_page, translation_action
from . import faq_views, gallery_views
from .blog_views import blog_list_view, blog_detail_view
from .blog_admin_views import (admin_blog_list, admin_blog_create, admin_blog_edit,
                                admin_blog_delete, admin_tag_list)

urlpatterns = [
    # ── API / Search ──────────────────────────────────────────────────────────
    path('api/global-search/', global_search_ajax, name='global_search'),

    # ── Public Views ──────────────────────────────────────────────────
    path('portfolio/', RedirectView.as_view(pattern_name='clinic_portfolio', permanent=True), name='clinic_portfolio_legacy'),
    path('testimonials/', testimonials_page, name='public_testimonials'),
    path('faq/', faq_views.faq_page, name='clinic_faq'),
    path('review/', faq_views.review_page, name='clinic_review'),
    path('terms/', faq_views.terms_page, name='clinic_terms'),
    path('gallery/', gallery_views.gallery_page, name='public_gallery'),
    path('about/', clinic_about_page_view, name='clinic_about_page'),
    path('practitioners/<b64uuid:pk>/', practitioner_detail_view, name='practitioner_detail'),
    path('ajax/submit-review/', submit_review_ajax, name='submit_review_ajax'),
    path('reviews/withdraw/<str:token>/', review_withdraw, name='review_withdraw'),
    path('ajax/book-appointment/', book_appointment_ajax, name='book_appointment_ajax'),

    # ── Public Event Detail ───────────────────────────────────────────
    path('events/', pev.public_event_list, name='public_event_list'),
    path('events/<b64uuid:pk>/', pev.public_event_detail, name='event_detail'),
    path('events/<b64uuid:pk>/register/', pev.register_for_event, name='event_register_ajax'),
    path('events/<b64uuid:pk>/calendar.ics', pev.event_ics, name='event_ics'),
    path('events/registration/<str:token>/', pev.registration_manage, name='event_registration_manage'),
    path('events/registration/<str:token>/calendar.ics', pev.registration_ics, name='registration_ics'),

    # ── Public Course Detail ──────────────────────────────────────────
    path('courses/<b64uuid:pk>/', course_detail_view, name='course_detail'),
    path('courses/<b64uuid:pk>/register/', pcv.register_for_course, name='course_register_ajax'),
    path('courses/registration/<str:token>/', pcv.registration_manage, name='course_registration_manage'),
    path('courses/registration/<str:token>/card/<str:side>.png', student_views.my_card_png, name='course_student_card'),
    path('courses/registration/<str:token>/card.pdf', student_views.my_card_pdf, name='course_student_card_pdf'),
    path('courses/verify/<str:code>/', student_views.student_verify, name='student_verify'),

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
    path('admin/featured-patients/', gallery_views.admin_featured, name='admin_featured'),
    path('admin/featured-patients/<uuid:pk>/', gallery_views.admin_featured_edit, name='admin_featured_edit'),
    path('admin/featured-patients/<uuid:pk>/delete/', gallery_views.admin_featured_delete, name='admin_featured_delete'),
    path('admin/gallery/', gallery_views.admin_gallery, name='admin_gallery'),
    path('admin/gallery/<uuid:pk>/', gallery_views.admin_gallery_edit, name='admin_gallery_edit'),
    path('admin/gallery/<uuid:pk>/delete/', gallery_views.admin_gallery_delete, name='admin_gallery_delete'),
    path('admin/faqs/', faq_views.admin_faqs, name='admin_faqs'),
    path('admin/faqs/<uuid:pk>/', faq_views.admin_faq_edit, name='admin_faq_edit'),
    path('admin/faqs/<uuid:pk>/delete/', faq_views.admin_faq_delete, name='admin_faq_delete'),
    path('admin/testimonials/', testimonials_list, name='admin_testimonials'),
    path('admin/testimonials/create/', testimonial_create, name='admin_testimonial_create'),
    path('admin/testimonials/<uuid:pk>/edit/', testimonial_edit, name='admin_testimonial_edit'),
    path('admin/testimonials/<uuid:pk>/delete/', testimonial_delete, name='admin_testimonial_delete'),
    path('admin/testimonials/<uuid:pk>/toggle/', testimonial_toggle_publish, name='admin_testimonial_toggle'),
    path('admin/testimonials/<uuid:pk>/moderate/', testimonial_moderate, name='admin_testimonial_moderate'),

    path('admin/videos/', admin_videos, name='admin_videos'),
    path('admin/videos/sync/', admin_videos_sync, name='admin_videos_sync'),
    path('admin/videos/<uuid:pk>/', admin_video_edit, name='admin_video_edit'),
    path('admin/videos/<uuid:pk>/toggle/', admin_video_toggle, name='admin_video_toggle'),
    path('admin/videos/<uuid:pk>/problem/', admin_video_problem, name='admin_video_problem'),
    path('admin/videos/<uuid:pk>/delete/', admin_video_delete, name='admin_video_delete'),
    path('admin/problems/', admin_problems, name='admin_problems'),
    path('admin/problems/<uuid:pk>/delete/', admin_problem_delete, name='admin_problem_delete'),

    path('admin/translations/', translations_page, name='admin_translations'),
    path('admin/translations/action/', translation_action, name='admin_translation_action'),

    # ── Admin Activity Log ──────────────────────────────────────────
    path('admin/activity-log/', activity_log_view, name='admin_activity_log'),
    path('admin/activity-log/<uuid:pk>/revert/', revert_audit_log_view, name='admin_revert_log'),
]
