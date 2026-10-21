from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [('clinic', '0016_safe_video_field')]

    operations = [
        migrations.AddField(
            model_name='testimonialvideo', name='tags',
            field=models.CharField(blank=True, help_text='Comma-separated; imported from YouTube.', max_length=500, verbose_name='Tags'),
        ),
    ]
