from django.urls import path

from . import views

urlpatterns = [
    path('', views.center, name='notification_center'),
    path('summary/', views.summary, name='notification_summary'),
    path('mark-all-read/', views.mark_all_read, name='notification_mark_all_read'),
    path('preferences/', views.preferences, name='notification_preferences'),
    path('deliveries/', views.deliveries, name='notification_deliveries'),
    path('deliveries/<int:pk>/retry/', views.retry_delivery, name='notification_retry'),
    path('<uuid:pk>/read/', views.mark_read, name='notification_read'),
    path('<uuid:pk>/unread/', views.mark_unread, name='notification_unread'),
    path('<uuid:pk>/archive/', views.archive, name='notification_archive'),
    path('<uuid:pk>/unarchive/', views.unarchive, name='notification_unarchive'),
    path('<uuid:pk>/open/', views.open_notification, name='notification_open'),
]
