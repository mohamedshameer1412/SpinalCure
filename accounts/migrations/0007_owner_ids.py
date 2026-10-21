import random

from django.db import migrations, models

LETTERS = 'ABCDEFGHJKLMNPQRSTUVWXYZ'
OWNER_ROLES = ('superadmin', 'owner', 'clinicadmin')


def new_ids(apps, schema_editor):
    """Re-number every staff id as four digits + three letters, and mark owner-level people's cards as Owner cards."""
    Profile = apps.get_model('accounts', 'StaffProfile')
    Card = apps.get_model('idcards', 'IDCard')
    used = set()
    for p in Profile.objects.all():
        while True:
            code = f'{random.randint(1000, 9999)}-' + ''.join(random.choice(LETTERS) for _ in range(3))
            if code not in used:
                used.add(code)
                break
        Profile.objects.filter(pk=p.pk).update(employee_id=code)
    for c in Card.objects.select_related('holder__user'):
        owner = c.holder.user.role in OWNER_ROLES or c.holder.user.is_superuser
        want = 'owner' if owner else 'staff'
        if c.card_type != want:
            Card.objects.filter(pk=c.pk).update(card_type=want)


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0006_private_uploads'),
        ('idcards', '0002_id_card_personal_details'),
    ]

    operations = [
        migrations.AlterField(
            model_name='staffprofile', name='employee_id',
            field=models.CharField(editable=False, help_text='Immutable. Four digits and three letters, unique for everyone, e.g. 4827-KQM.',
                                   max_length=20, unique=True),
        ),
        migrations.RunPython(new_ids, migrations.RunPython.noop),
    ]
