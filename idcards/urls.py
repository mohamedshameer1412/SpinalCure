from django.urls import path

from . import views

urlpatterns = [
    path('', views.dashboard, name='idcard_dashboard'),
    path('issue/', views.issue, name='idcard_issue'),
    path('mine/', views.mine, name='idcard_mine'),
    path('branding/', views.branding, name='idcard_branding'),
    path('<uuid:pk>/', views.detail, name='idcard_detail'),
    path('<uuid:pk>/action/', views.action, name='idcard_action'),
    path('<uuid:pk>/<str:side>.png', views.card_png, name='idcard_png'),
    path('<uuid:pk>/card.pdf', views.card_pdf, name='idcard_pdf'),
]

# Public routes (no language prefix: the QR printed on a card must never change).
public_urlpatterns = [
    path('verify/<str:card_id>/', views.verify, name='idcard_verify'),
    path('share/<str:token>/', views.share, name='idcard_share'),
    path('share/<str:token>/card.png', views.share_image, name='idcard_share_image'),
]
