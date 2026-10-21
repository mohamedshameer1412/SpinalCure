from django import forms
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from clinic.models import ClinicProfile, Practitioner
from .models import CustomUser, StaffProfile


class UserAdminForm(forms.ModelForm):
    """Create/edit a user, with optional organisational (staff) profile details."""
    password = forms.CharField(required=False, widget=forms.PasswordInput(render_value=False))
    designation = forms.CharField(required=False, max_length=120)
    department = forms.CharField(required=False, max_length=120)
    joined_on = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    employment_status = forms.ChoiceField(required=False, choices=StaffProfile.STATUS_CHOICES)
    # personal details printed on the ID card
    gender = forms.ChoiceField(required=False, choices=[('', '---------')] + StaffProfile.GENDER_CHOICES)
    date_of_birth = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    blood_group = forms.ChoiceField(required=False, choices=[('', '---------')] + StaffProfile.BLOOD_CHOICES)
    address = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 3}))
    emergency_contact_name = forms.CharField(required=False, max_length=120)
    emergency_contact_phone = forms.CharField(required=False, max_length=20)
    # practitioner (doctor) profile, so name / photo / phone / email are typed once, here
    practitioner_mode = forms.ChoiceField(required=False, initial='none', choices=[
        ('none', _('Not a practitioner')), ('create', _('Create a practitioner profile from this account')),
        ('link', _('Link an existing practitioner'))])
    link_practitioner = forms.ModelChoiceField(required=False, queryset=Practitioner.objects.none(), empty_label=_('Choose…'))
    specialization = forms.CharField(required=False, max_length=300)
    qualifications = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 2}))
    experience_years = forms.IntegerField(required=False, min_value=0, max_value=80)

    class Meta:
        model = CustomUser
        fields = ['username', 'first_name', 'last_name', 'email', 'phone', 'photo', 'role', 'language']

    def __init__(self, *args, actor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.actor = actor
        self.fields['email'].required = True
        if not self.instance._state.adding:
            self.fields['username'].disabled = True  # not editable after creation
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'w-full')  # the kit styles native fields
        if not (actor and actor.is_superuser):
            # Only a super admin can mint another super admin.
            self.fields['role'].choices = [c for c in CustomUser.ROLE_CHOICES if c[0] != 'superadmin']
        mine = getattr(self.instance, 'practitioner', None) if not self.instance._state.adding else None
        self.fields['link_practitioner'].queryset = Practitioner.objects.filter(user__isnull=True, is_active=True)
        if mine:
            self.fields['practitioner_mode'].choices = [('create', _('Linked practitioner profile (keep)')), ('none', _('Unlink'))]
            self.fields['practitioner_mode'].initial = 'create'
            for f in ('specialization', 'qualifications', 'experience_years'):
                self.fields[f].initial = getattr(mine, f)
        profile = getattr(self.instance, 'staff_profile', None) if not self.instance._state.adding else None
        if profile:
            for f in ('designation', 'department', 'joined_on', 'employment_status', 'gender', 'date_of_birth', 'blood_group',
                      'address', 'emergency_contact_name', 'emergency_contact_phone'):
                self.fields[f].initial = getattr(profile, f)

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        clash = CustomUser.objects.filter(email__iexact=email).exclude(pk=self.instance.pk)
        if clash.exists():
            raise forms.ValidationError(_('A user with this email already exists.'))
        return email

    def clean_password(self):
        pw = self.cleaned_data.get('password', '')
        if self.instance._state.adding and not pw:
            raise forms.ValidationError(_('Password is required.'))
        if pw:
            validate_password(pw, self.instance if not self.instance._state.adding else None)
        return pw

    def clean_role(self):
        role = self.cleaned_data['role']
        if not self.instance._state.adding and self.actor and self.instance.pk == self.actor.pk and role != self.instance.role:
            raise forms.ValidationError(_('You cannot change your own role.'))
        return role

    def clean(self):
        data = super().clean()
        if data.get('role') in ('owner', 'staff') and not data.get('designation'):
            self.add_error('designation', _('Designation is required for owners and staff.'))
        if data.get('practitioner_mode') == 'link' and not data.get('link_practitioner'):
            self.add_error('link_practitioner', _('Choose the practitioner to link.'))
        return data

    def _save_practitioner(self, user):
        data = self.cleaned_data
        mode = data.get('practitioner_mode') or 'none'
        mine = getattr(user, 'practitioner', None) if user.pk else None
        if mode == 'none':
            if mine:
                mine.user = None
                mine.save(update_fields=['user'])
            return
        pr = mine or (data['link_practitioner'] if mode == 'link' else Practitioner())
        pr.user = user
        # the account is the source of truth for identity: only blanks on an existing profile are filled
        for field, value in (('name', user.get_full_name() or user.username), ('email', user.email), ('phone', user.phone or ''),
                             ('title', data.get('designation') or '')):
            if not getattr(pr, field):
                setattr(pr, field, value)
        if user.photo and not pr.photo:
            pr.photo = user.photo.name                         # same stored file, not a second copy
        for f in ('specialization', 'qualifications'):
            if data.get(f):
                setattr(pr, f, data[f])
        if data.get('experience_years') is not None:
            pr.experience_years = data['experience_years']
        pr.save()

    def save(self, commit=True):
        user = super().save(commit=False)
        pw = self.cleaned_data.get('password')
        if pw:
            user.set_password(pw)
        user.save()
        data = self.cleaned_data
        if data.get('designation') or data['role'] in ('owner', 'staff'):
            clinic = ClinicProfile.objects.first()
            if clinic:
                profile = getattr(user, 'staff_profile', None) or StaffProfile(user=user, clinic=clinic)
                profile.designation = data['designation']
                profile.department = data.get('department', '')
                profile.joined_on = data.get('joined_on') or profile.joined_on or timezone.localdate()
                if data.get('employment_status'):
                    profile.employment_status = data['employment_status']
                for f in ('gender', 'date_of_birth', 'blood_group', 'address', 'emergency_contact_name', 'emergency_contact_phone'):
                    setattr(profile, f, data.get(f) or ('' if f != 'date_of_birth' else None))
                profile.save()
        self._save_practitioner(user)
        return user
