"""Public FAQ page and review landing page, plus the FAQ editor for staff."""
from django import forms
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext, gettext_lazy as _
from django.views.decorators.http import require_POST

from spinalcure.decorators import superadmin_required
from .models import FAQ, ProblemCategory


def faq_page(request):
    faqs = list(FAQ.objects.filter(is_published=True).select_related('problem'))
    groups, general = {}, []
    for f in faqs:
        (groups.setdefault(f.problem, []) if f.problem else general).append(f)
    sections = [(p, items) for p, items in sorted(groups.items(), key=lambda kv: (kv[0].order, kv[0].name))]
    if general:
        sections.insert(0, (None, general))
    return render(request, 'clinic/faq.html', {'sections': sections, 'faqs': faqs})


def terms_page(request):
    return render(request, 'clinic/terms.html')


def review_page(request):
    """Where review-request emails land: review us on Google, or here."""
    return render(request, 'clinic/review.html')


# ── Staff ─────────────────────────────────────────────────────────────────────────────────────────────

class FAQForm(forms.ModelForm):
    class Meta:
        model = FAQ
        fields = ['question', 'answer', 'problem', 'order', 'reviewed_by', 'is_published']
        widgets = {'answer': forms.Textarea(attrs={'rows': 6})}
        help_texts = {'answer': _('Plain words, short paragraphs. Describe what treatment involves and when to '
                                  'see a doctor; do not promise cures.')}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['problem'].queryset = ProblemCategory.objects.filter(is_active=True)
        self.fields['problem'].empty_label = gettext('General')

    def clean(self):
        data = super().clean()
        if data.get('is_published') and not (data.get('reviewed_by') or '').strip():
            self.add_error('reviewed_by', gettext('Enter who checked this answer before publishing it.'))
        return data


@superadmin_required
def admin_faqs(request):
    form = FAQForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        faq = form.save()
        messages.success(request, gettext('Question added.'))
        return redirect('admin_faq_edit', pk=faq.pk)
    faqs = FAQ.objects.select_related('problem')
    return render(request, 'clinic/admin/faqs.html', {
        'faqs': faqs, 'form': form, 'published': sum(f.is_published for f in faqs)})


@superadmin_required
def admin_faq_edit(request, pk):
    faq = get_object_or_404(FAQ, pk=pk)
    form = FAQForm(request.POST or None, instance=faq)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, gettext('Question saved.'))
        return redirect('admin_faqs')
    return render(request, 'clinic/admin/faq_form.html', {'form': form, 'faq': faq})


@superadmin_required
@require_POST
def admin_faq_delete(request, pk):
    get_object_or_404(FAQ, pk=pk).delete()
    messages.success(request, gettext('Question deleted.'))
    return redirect('admin_faqs')
