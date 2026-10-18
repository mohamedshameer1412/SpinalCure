from django import forms
from django.utils.translation import gettext_lazy as _

from accounts.models import StaffProfile
from .models import IDCard, IDCardBranding

CSS = 'w-full rounded-xl border-gray-200 text-sm focus:ring-2 focus:ring-green-500 focus:border-green-500'


class IssueForm(forms.Form):
    holder = forms.ModelChoiceField(queryset=StaffProfile.objects.none(), label=_('Person'))
    expires_on = forms.DateField(required=False, label=_('Expires on'), widget=forms.DateInput(attrs={'type': 'date'}))
    show_phone = forms.BooleanField(required=False, initial=True, label=_('Show phone on the card'))
    show_email = forms.BooleanField(required=False, label=_('Show email on the card'))
    show_emergency_contact = forms.BooleanField(required=False, label=_('Show emergency contact on the back'))
    show_blood_group = forms.BooleanField(required=False, label=_('Show blood group on the back'))
    show_skills = forms.BooleanField(required=False, label=_('Show skills on the back'))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        live = IDCard.objects.filter(status__in=('active', 'deactivated')).values_list('holder_id', flat=True)
        self.fields['holder'].queryset = (StaffProfile.objects.select_related('user')
                                          .exclude(pk__in=live).filter(user__is_active=True)
                                          .exclude(employment_status__in=('terminated', 'suspended')))
        self.fields['holder'].label_from_instance = lambda p: f'{p.employee_id} — {p.user.get_full_name() or p.user.username} ({p.designation})'
        for f in self.fields.values():
            if not isinstance(f.widget, forms.CheckboxInput):
                f.widget.attrs.setdefault('class', CSS)

    def options(self):
        d = self.cleaned_data
        return {k: d[k] for k in ('show_phone', 'show_email', 'show_emergency_contact', 'show_blood_group', 'show_skills')}


class BrandingForm(forms.ModelForm):
    class Meta:
        model = IDCardBranding
        fields = ['primary_color', 'accent_color', 'tagline', 'org_url', 'legal_footer', 'show_photo_on_verify']
        widgets = {'primary_color': forms.TextInput(attrs={'type': 'color'}),
                   'accent_color': forms.TextInput(attrs={'type': 'color'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            if not isinstance(f.widget, forms.CheckboxInput):
                f.widget.attrs.setdefault('class', CSS)
