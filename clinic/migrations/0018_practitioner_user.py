import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('clinic', '0017_video_tags'),
    ]

    operations = [
        migrations.AddField(
            model_name='practitioner', name='user',
            field=models.OneToOneField(blank=True, db_constraint=False, editable=False, null=True,
                                       on_delete=django.db.models.deletion.SET_NULL, related_name='practitioner',
                                       to=settings.AUTH_USER_MODEL),
        ),
    ]
