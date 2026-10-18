from django import forms
from django.utils.translation import gettext_lazy as _

from .models import BookingSettings, DoctorAvailability, TimeOff

CSS = 'w-full rounded-xl border-gray-200 text-sm focus:ring-2 focus:ring-green-500 focus:border-green-500'


class _Styled(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            if not isinstance(f.widget, forms.CheckboxInput):
                f.widget.attrs.setdefault('class', CSS)


class ShiftForm(_Styled):
    class Meta:
        model = DoctorAvailability
        fields = ['day_of_week', 'start_time', 'end_time', 'slot_duration_minutes', 'buffer_minutes',
                  'break_start', 'break_end', 'appointment_type', 'max_appointments',
                  'valid_from', 'valid_until', 'is_available']
        widgets = {
            'start_time': forms.TimeInput(attrs={'type': 'time'}, format='%H:%M'),
            'end_time': forms.TimeInput(attrs={'type': 'time'}, format='%H:%M'),
            'break_start': forms.TimeInput(attrs={'type': 'time'}, format='%H:%M'),
            'break_end': forms.TimeInput(attrs={'type': 'time'}, format='%H:%M'),
            'valid_from': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'valid_until': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
        }


class TimeOffForm(_Styled):
    class Meta:
        model = TimeOff
        fields = ['kind', 'start_date', 'end_date', 'start_time', 'end_time', 'reason']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'end_date': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'start_time': forms.TimeInput(attrs={'type': 'time'}, format='%H:%M'),
            'end_time': forms.TimeInput(attrs={'type': 'time'}, format='%H:%M'),
        }


class BookingSettingsForm(_Styled):
    class Meta:
        model = BookingSettings
        fields = ['min_notice_minutes', 'max_advance_days', 'default_duration_minutes', 'cancel_cutoff_hours',
                  'max_active_per_contact', 'allow_public_booking', 'reminder_offsets_minutes',
                  'followup_lead_days', 'missed_grace_minutes', 'auto_mark_no_show']

    def clean_default_duration_minutes(self):
        v = self.cleaned_data['default_duration_minutes']
        if not 5 <= v <= 480:
            raise forms.ValidationError(_('Must be between 5 and 480 minutes.'))
        return v
