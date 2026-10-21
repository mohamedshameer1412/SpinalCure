"""Session package catalogue (prepaid bundles of sittings) for management."""
from django import forms
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext
from django.views.decorators.http import require_POST

from spinalcure.rbac import require_capability
from .models import SessionPackage


class PackageForm(forms.ModelForm):
    class Meta:
        model = SessionPackage
        fields = ['name', 'sittings', 'price', 'validity_days', 'description', 'order', 'is_active']

    def clean_sittings(self):
        v = self.cleaned_data['sittings']
        if not 1 <= v <= 200:
            raise forms.ValidationError(gettext('Enter between 1 and 200 sittings.'))
        return v


@require_capability('packages.manage')
def packages(request):
    form = PackageForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, gettext('Package added.'))
        return redirect('session_packages')
    return render(request, 'patients/packages.html', {'packages': SessionPackage.objects.all(), 'form': form})


@require_capability('packages.manage')
def package_edit(request, pk):
    pkg = get_object_or_404(SessionPackage, pk=pk)
    form = PackageForm(request.POST or None, instance=pkg)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, gettext('Package saved.'))
        return redirect('session_packages')
    return render(request, 'patients/package_form.html', {'form': form, 'package': pkg})


@require_capability('packages.manage')
@require_POST
def package_delete(request, pk):
    """Plans started from a package keep their own copy of its sittings and price, so deleting is safe."""
    get_object_or_404(SessionPackage, pk=pk).delete()
    messages.success(request, gettext('Package deleted.'))
    return redirect('session_packages')
