from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    PaymentViewSet, payment_list_view, payment_invoice_view, send_invoice_email_view,
    payment_pdf_download_view,
    expense_list_view, expense_create_view, expense_edit_view, expense_delete_view,
    export_expenses_excel, export_expenses_csv, export_expenses_pdf, export_expenses_copy, export_expenses_print,
    export_payments_excel, export_payments_csv, export_payments_pdf, export_payments_copy, export_payments_print,
    payment_create_view, payment_edit_view, payment_delete_view
)

router = DefaultRouter()
router.register(r'', PaymentViewSet, basename='api-payment')

urlpatterns = [
    path('', payment_list_view, name='payment_list'),
    path('<b64uuid:pk>/invoice/', payment_invoice_view, name='payment_invoice'),
    path('<b64uuid:pk>/download-receipt/', payment_pdf_download_view, name='payment_pdf_download'),
    path('<b64uuid:pk>/send-email/', send_invoice_email_view, name='send_invoice_email'),
    path('export/excel/', export_payments_excel, name='export_payments_excel'),
    path('export/csv/', export_payments_csv, name='export_payments_csv'),
    path('export/pdf/', export_payments_pdf, name='export_payments_pdf'),
    path('export/copy/', export_payments_copy, name='export_payments_copy'),
    path('export/print/', export_payments_print, name='export_payments_print'),
    path('api/', include(router.urls)),
    # Expenses
    path('expenses/', expense_list_view, name='expense_list'),
    path('expenses/export/excel/', export_expenses_excel, name='export_expenses_excel'),
    path('expenses/export/csv/', export_expenses_csv, name='export_expenses_csv'),
    path('expenses/export/pdf/', export_expenses_pdf, name='export_expenses_pdf'),
    path('expenses/export/copy/', export_expenses_copy, name='export_expenses_copy'),
    path('expenses/export/print/', export_expenses_print, name='export_expenses_print'),
    path('expenses/create/', expense_create_view, name='expense_create'),
    path('expenses/<b64uuid:pk>/edit/', expense_edit_view, name='expense_edit'),
    path('expenses/<b64uuid:pk>/delete/', expense_delete_view, name='expense_delete'),

    path('create/', payment_create_view, name='payment_create'),
    path('<b64uuid:pk>/edit/', payment_edit_view, name='payment_edit'),
    path('<b64uuid:pk>/delete/', payment_delete_view, name='payment_delete'),
]
