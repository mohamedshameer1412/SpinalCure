from zoneinfo import available_timezones

from django import forms
from django.utils.translation import gettext_lazy as _

from .models import Event

CSS = 'w-full'  # the kit styles native fields


class EventForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = ['title', 'event_type', 'description', 'presenter', 'image', 'date', 'start_time', 'end_time',
                  'timezone', 'language', 'is_online', 'venue', 'meeting_provider', 'meeting_link',
                  'meeting_passcode', 'access_instructions', 'max_participants', 'waitlist_enabled',
                  'registration_required', 'registration_deadline', 'reminder_offsets_minutes', 'fees']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'start_time': forms.TimeInput(attrs={'type': 'time'}, format='%H:%M'),
            'end_time': forms.TimeInput(attrs={'type': 'time'}, format='%H:%M'),
            'registration_deadline': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
            'description': forms.Textarea(attrs={'rows': 5}),
            'access_instructions': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['timezone'] = forms.ChoiceField(
            label=_('Time zone'), choices=[(z, z) for z in sorted(available_timezones())],
            initial=self.instance.timezone if self.instance.pk else None)
        self.fields['registration_deadline'].input_formats = ['%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M']
        for f in self.fields.values():
            if not isinstance(f.widget, (forms.CheckboxInput, forms.ClearableFileInput)):
                f.widget.attrs.setdefault('class', CSS)

    def clean_image(self):
        img = self.cleaned_data.get('image')
        if img and hasattr(img, 'size'):
            if img.size > 5 * 1024 * 1024:
                raise forms.ValidationError(_('Image must be 5 MB or smaller.'))
            ctype = getattr(img, 'content_type', '') or ''
            if ctype and ctype not in ('image/jpeg', 'image/png', 'image/webp'):
                raise forms.ValidationError(_('Upload a JPEG, PNG or WebP image.'))
        return img

    def clean_meeting_link(self):
        link = (self.cleaned_data.get('meeting_link') or '').strip()
        if link and not link.lower().startswith('https://'):
            raise forms.ValidationError(_('Meeting links must start with https://'))
        return link
