from django.urls import path
from .views import DashboardStatsAPIView

urlpatterns = [
    path('dashboard-stats/', DashboardStatsAPIView.as_view(), name='api_dashboard_stats'),
]
