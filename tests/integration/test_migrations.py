import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_existing_appointments_get_unique_manage_tokens_and_survive_migration():
    executor = MigrationExecutor(connection)
    before = [('appointments', '0003_appointment_guest_email_appointment_guest_name_and_more')]
    executor.migrate(before)
    old_apps = executor.loader.project_state(before).apps
    Appointment = old_apps.get_model('appointments', 'Appointment')
    for i in range(5):
        Appointment.objects.create(guest_name=f'G{i}', guest_phone='9000000000', appointment_date='2030-01-07',
                                   appointment_time=f'1{i}:00', duration_minutes=30, status='scheduled')

    executor = MigrationExecutor(connection)
    executor.migrate(executor.loader.graph.leaf_nodes())
    new_apps = executor.loader.project_state(executor.loader.graph.leaf_nodes()).apps
    Appointment = new_apps.get_model('appointments', 'Appointment')
    tokens = list(Appointment.objects.values_list('manage_token', flat=True))
    assert len(tokens) == 5 and len(set(tokens)) == 5 and all(len(t) >= 20 for t in tokens)
    assert Appointment.objects.filter(booked_via='staff').count() == 5      # default applied to old rows
