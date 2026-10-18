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


@pytest.mark.django_db(transaction=True)
def test_event_migration_keeps_published_events_published_and_backfills_registrations():
    executor = MigrationExecutor(connection)
    before = [('events', '0006_alter_eventfeedback_registration')] if False else None
    leaf_before = [n for n in executor.loader.graph.leaf_nodes() if n[0] == 'events']
    prior = sorted(k for k in executor.loader.graph.nodes if k[0] == 'events' and k[1] < '0007')[-1]
    executor.migrate([prior])
    old_apps = executor.loader.project_state([prior]).apps
    Event, Reg = old_apps.get_model('events', 'Event'), old_apps.get_model('events', 'EventRegistration')
    live = Event.objects.create(title='Live', date='2030-01-01', start_time='10:00', end_time='11:00', venue='x', is_published=True)
    draft = Event.objects.create(title='Draft', date='2030-01-01', start_time='10:00', end_time='11:00', venue='x', is_published=False)
    for i in range(3):
        Reg.objects.create(event=live, name=f'R{i}', phone='+91 98765 4321' + str(i))

    executor = MigrationExecutor(connection)
    leaves = executor.loader.graph.leaf_nodes()
    executor.migrate(leaves)
    new_apps = executor.loader.project_state(leaves).apps
    Event, Reg = new_apps.get_model('events', 'Event'), new_apps.get_model('events', 'EventRegistration')
    assert Event.objects.get(title='Live').status == 'published'
    assert Event.objects.get(title='Draft').status == 'draft'
    tokens = list(Reg.objects.values_list('access_token', flat=True))
    assert len(set(tokens)) == 3 and all(tokens)
    assert set(Reg.objects.values_list('phone_key', flat=True)) == {'9876543210', '9876543211', '9876543212'}
    assert set(Reg.objects.values_list('status', flat=True)) == {'confirmed'}


@pytest.mark.django_db(transaction=True)
def test_course_registrations_get_tokens_and_phone_keys():
    executor = MigrationExecutor(connection)
    prior = sorted(k for k in executor.loader.graph.nodes if k[0] == 'courses' and k[1] < '0005')[-1]
    executor.migrate([prior])
    old = executor.loader.project_state([prior]).apps
    Course, Batch, Reg = (old.get_model('courses', n) for n in ('Course', 'CourseBatch', 'CourseRegistration'))
    course = Course.objects.create(title='C', short_description='d', is_published=True)
    batch = Batch.objects.create(course=course, name='B', start_date='2030-01-01')
    for i in range(3):
        Reg.objects.create(batch=batch, name=f'S{i}', phone=f'+91 90000 0000{i}')
    executor = MigrationExecutor(connection)
    leaves = executor.loader.graph.leaf_nodes()
    executor.migrate(leaves)
    new = executor.loader.project_state(leaves).apps
    Reg = new.get_model('courses', 'CourseRegistration')
    assert len(set(Reg.objects.values_list('access_token', flat=True))) == 3
    assert set(Reg.objects.values_list('phone_key', flat=True)) == {'9000000000', '9000000001', '9000000002'}
