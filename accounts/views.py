from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.translation import gettext, gettext_lazy as _

from .models import CustomUser


class ProfileForm(forms.ModelForm):
    """A user's own profile. Email is the login identifier, so it must stay unique (case-insensitive)."""
    class Meta:
        model = CustomUser
        fields = ['first_name', 'last_name', 'email', 'phone', 'bio']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].required = True

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if CustomUser.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError(_('This email is already used by another account.'))
        return email


@login_required
def settings_view(request):
    form = ProfileForm(request.POST or None, instance=request.user)
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            messages.success(request, gettext('Profile updated successfully!'))
            return redirect('settings')
        for errors in form.errors.values():
            for e in errors:
                messages.error(request, e)
    return render(request, 'accounts/settings.html', {'user': request.user, 'form': form})
