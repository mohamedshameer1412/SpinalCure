from django.urls import path

from . import views

urlpatterns = [
    path('', views.card_list, name='idcard_list'),
    path('issue/', views.card_form, name='idcard_issue'),
    path('mine/', views.my_card, name='my_idcard'),
    path('<int:pk>/', views.card_detail, name='idcard_detail'),
    path('<int:pk>/edit/', views.card_form, name='idcard_edit'),
    path('<int:pk>/action/', views.card_action, name='idcard_action'),
]
public_urlpatterns = [
    path('verify/<str:token>/', views.verify, name='idcard_verify'),
    path('idcard/share/<str:token>/', views.share, name='idcard_share'),
]
