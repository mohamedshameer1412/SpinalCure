"""Public gallery and its staff manager (photos, uploaded videos, YouTube / Instagram links, featured spotlight)."""
from django import forms
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext
from django.views.decorators.http import require_POST

from spinalcure.decorators import superadmin_required
from spinalcure.uploads import UploadRejected, checked_image
from .models import FeaturedPatient, GalleryItem


def gallery_page(request):
    items = list(GalleryItem.objects.filter(is_published=True))
    return render(request, 'clinic/gallery.html', {
        'featured_patients': FeaturedPatient.objects.filter(is_published=True, consent_confirmed=True),
        'featured': [i for i in items if i.is_featured],
        'photos': [i for i in items if not i.is_featured and i.kind == 'photo'],
        'videos': [i for i in items if not i.is_featured and i.kind == 'video'],
    })


class GalleryForm(forms.ModelForm):
    class Meta:
        model = GalleryItem
        fields = ['kind', 'title', 'caption', 'image', 'video_file', 'video_url', 'is_featured', 'featured_label',
                  'order', 'is_published']
        widgets = {'caption': forms.Textarea(attrs={'rows': 3})}

    def clean_image(self):
        img = self.cleaned_data.get('image')
        if img and hasattr(img, 'content_type'):           # a new upload (not the stored file)
            try:
                checked_image(img)
            except UploadRejected as e:
                raise forms.ValidationError(str(e))
        return img


@superadmin_required
def admin_gallery(request):
    if request.method == 'POST' and request.FILES.getlist('photos'):
        # quick add: several photos at once, titled from the form (or the file name)
        title = request.POST.get('bulk_title', '').strip()
        added = 0
        for f in request.FILES.getlist('photos')[:30]:
            original = f.name.rsplit('.', 1)[0][:200]           # checked_image renames the upload
            try:
                checked_image(f)
            except UploadRejected as e:
                messages.error(request, f'{original}: {e}')
                continue
            GalleryItem.objects.create(kind='photo', title=title or original, image=f)
            added += 1
        if added:
            messages.success(request, gettext('%(n)s photos added.') % {'n': added})
        return redirect('admin_gallery')
    form = GalleryForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, gettext('Added to the gallery.'))
        return redirect('admin_gallery')
    return render(request, 'clinic/admin/gallery.html', {'items': GalleryItem.objects.all(), 'form': form})


@superadmin_required
def admin_gallery_edit(request, pk):
    item = get_object_or_404(GalleryItem, pk=pk)
    form = GalleryForm(request.POST or None, request.FILES or None, instance=item)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, gettext('Gallery item saved.'))
        return redirect('admin_gallery')
    return render(request, 'clinic/admin/gallery_form.html', {'form': form, 'item': item})


@superadmin_required
@require_POST
def admin_gallery_delete(request, pk):
    item = get_object_or_404(GalleryItem, pk=pk)
    for f in (item.image, item.video_file):
        if f:
            f.delete(save=False)
    item.delete()
    messages.success(request, gettext('Removed from the gallery.'))
    return redirect('admin_gallery')


# ── Featured patients ────────────────────────────────────────────────────────────────────────────────

class FeaturedPatientForm(forms.ModelForm):
    class Meta:
        model = FeaturedPatient
        fields = ['name', 'profession', 'photo', 'note', 'consent_confirmed', 'order', 'is_published']

    def clean_photo(self):
        img = self.cleaned_data.get('photo')
        if img and hasattr(img, 'content_type'):
            try:
                checked_image(img)
            except UploadRejected as e:
                raise forms.ValidationError(str(e))
        return img


@superadmin_required
def admin_featured(request):
    form = FeaturedPatientForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, gettext('Featured patient added.'))
        return redirect('admin_featured')
    return render(request, 'clinic/admin/featured.html', {'people': FeaturedPatient.objects.all(), 'form': form})


@superadmin_required
def admin_featured_edit(request, pk):
    person = get_object_or_404(FeaturedPatient, pk=pk)
    form = FeaturedPatientForm(request.POST or None, request.FILES or None, instance=person)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, gettext('Featured patient saved.'))
        return redirect('admin_featured')
    return render(request, 'clinic/admin/featured_form.html', {'form': form, 'person': person})


@superadmin_required
@require_POST
def admin_featured_delete(request, pk):
    person = get_object_or_404(FeaturedPatient, pk=pk)
    person.photo.delete(save=False)
    person.delete()
    messages.success(request, gettext('Featured patient removed.'))
    return redirect('admin_featured')
