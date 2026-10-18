"""
Races N threads for one slot. On SQLite this exercises the transaction + the partial UNIQUE constraint
backstop; it does NOT prove the MySQL SELECT ... FOR UPDATE path (needs a MySQL instance).
"""
import threading
import time as time_module
from datetime import date, datetime, time, timedelta

import pytest
from django.db import OperationalError, connection
from django.utils import timezone

from appointments import scheduling as sch
from appointments.models import Appointment, DoctorAvailability
from clinic.models import ClinicProfile, Practitioner

TZ = timezone.get_default_timezone()
NOW = timezone.make_aware(datetime(2030, 1, 7, 8, 0), TZ)


@pytest.mark.django_db(transaction=True)
def test_simultaneous_bookings_for_one_slot_produce_exactly_one_appointment(settings):
    settings.NOTIFY_SEND_ON_COMMIT = False
    ClinicProfile.objects.create(name='C', address='x', phone='9876543210')
    doc = Practitioner.objects.create(name='Dr Rao', is_active=True)
    DoctorAvailability.objects.create(practitioner=doc, day_of_week=0, start_time=time(10, 0), end_time=time(11, 0))
    outcomes, barrier = [], threading.Barrier(8)

    def attempt(i):
        try:
            barrier.wait(timeout=5)
            for _retry in range(40):             # SQLite reports writer contention as an error; a client retries
                try:
                    sch.book(practitioner=doc, day=date(2030, 1, 7), start_time=time(10, 0), guest_name=f'G{i}',
                             guest_phone=f'90000000{i:02d}', now=NOW)
                    outcomes.append('booked')
                except sch.SchedulingError as exc:
                    outcomes.append(exc.code)
                except OperationalError:
                    time_module.sleep(0.05)
                    continue
                break
            else:
                outcomes.append('db_locked')
        finally:
            connection.close()

    threads = [threading.Thread(target=attempt, args=(i,)) for i in range(8)]
    [t.start() for t in threads]; [t.join(15) for t in threads]

    assert Appointment.objects.filter(practitioner=doc, status='scheduled').count() == 1
    assert outcomes.count('booked') == 1
    assert outcomes.count('conflict') == 7 and 'db_locked' not in outcomes
