from django.urls import path

from . import views

urlpatterns = [
    path('', views.center, name='notification_center'),
    path('<int:pk>/open/', views.open_notification, name='notification_open'),
    path('action/', views.bulk_action, name='notification_action'),
    path('preferences/', views.preferences, name='notification_preferences'),
    path('deliveries/', views.deliveries, name='notification_deliveries'),
]
