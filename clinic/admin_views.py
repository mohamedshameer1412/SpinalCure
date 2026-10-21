from spinalcure.uploads import checked_image, reject_bad_uploads
from django.utils.translation import gettext
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib import messages
from django.views.decorators.http import require_POST
from spinalcure.decorators import superadmin_required
from .models import ClinicProfile, Practitioner, ClinicService, ClinicAboutImage, ClinicTestimonial, ProblemCategory

@superadmin_required
@reject_bad_uploads
def clinic_setup_view(request):
    clinic = ClinicProfile.objects.first()
    if not clinic:
        clinic = ClinicProfile.objects.create(name='SpinalCure')

    ICON_CHOICES = [
        ('bi-activity', 'Activity (ECG/Vitals)'),
        ('bi-bandaid', 'Bandaid (Healing)'),
        ('bi-capsule', 'Capsule (Medicine)'),
        ('bi-clipboard2-pulse', 'Clipboard Pulse (Diagnosis)'),
        ('bi-droplet', 'Droplet (Blood/Liquid)'),
        ('bi-ear', 'Ear (Auricular)'),
        ('bi-flower1', 'Flower (Holistic/Natural)'),
        ('bi-heart-pulse', 'Heart Pulse (Cardio)'),
        ('bi-hospital', 'Hospital'),
        ('bi-lungs', 'Lungs (Respiratory)'),
        ('bi-moisture', 'Moisture (Therapy)'),
        ('bi-person-arms-up', 'Person Arms Up (Recovery)'),
        ('bi-person-wheelchair', 'Wheelchair (Rehab)'),
        ('bi-prescription2', 'Prescription'),
        ('bi-thermometer', 'Thermometer'),
        ('bi-yin-yang', 'Yin Yang (Balance/Acupuncture)'),
        ('bi-star', 'Star (Featured)'),
        ('bi-check-circle', 'Check (Success)'),
    ]

    if request.method == 'POST':
        data = request.POST
        section_type = data.get('section_type')

        if section_type == 'general':
            fields = ['name', 'tagline', 'registration_number', 'phone', 'email', 'address']
            for field in fields:
                setattr(clinic, field, data.get(field, ''))
            messages.success(request, gettext('General information updated.'))

        elif section_type == 'billing':
            clinic.gstin = data.get('gstin', '')
            try:
                clinic.default_tax_percent = float(data.get('default_tax_percent', 0) or 0)
            except ValueError:
                clinic.default_tax_percent = 0
            messages.success(request, gettext('Billing & tax information updated.'))

        elif section_type == 'branding':
            clinic.hero_title = data.get('hero_title', '')
            clinic.hero_subtitle = data.get('hero_subtitle', '')
            clinic.footer_text = data.get('footer_text', '')
            if request.FILES.get('logo'): clinic.logo = checked_image(request.FILES['logo'])
            
            # Handle deleting existing hero carousel images
            delete_ids = request.POST.getlist('delete_hero_image_ids[]')
            if delete_ids:
                from spinalcure.utils import decode_b64uuid
                valid_ids = [decode_b64uuid(did) for did in delete_ids if decode_b64uuid(did)]
                clinic.hero_carousel_images.filter(id__in=valid_ids).delete()

            # Handle adding new hero carousel images
            new_images = request.FILES.getlist('new_hero_images[]')
            for order, img in enumerate(new_images):
                from clinic.models import HeroCarouselImage
                HeroCarouselImage.objects.create(
                    clinic=clinic,
                    image=checked_image(img),
                    order=clinic.hero_carousel_images.count() + order
                )

            messages.success(request, gettext('Branding & hero carousel updated.'))

        elif section_type == 'about':
            fields = ['about_label', 'about_title', 'about_stat1_number', 'about_stat1_label',
                      'about_stat2_number', 'about_stat2_label', 'about', 'about_quote']
            for field in fields:
                setattr(clinic, field, data.get(field, ''))
            
            # Handle About Images
            delete_img_ids = data.getlist('delete_about_image_ids[]')
            if delete_img_ids:
                ClinicAboutImage.objects.filter(id__in=delete_img_ids, clinic=clinic).delete()
            
            new_images = request.FILES.getlist('new_about_images[]')
            for img in new_images:
                ClinicAboutImage.objects.create(clinic=clinic, image=checked_image(img))
            messages.success(request, gettext('About section & legacy updated.'))

        elif section_type == 'services_header':
            clinic.services_label = data.get('services_label', '')
            clinic.services_title = data.get('services_title', '')
            clinic.services_description = data.get('services_description', '')
            messages.success(request, gettext('Services header updated.'))

        elif section_type == 'services_cards':
            # Handle Services dynamically
            delete_svc_ids = data.getlist('delete_service_ids[]')
            if delete_svc_ids:
                ClinicService.objects.filter(id__in=delete_svc_ids, clinic=clinic).delete()

            svc_ids = data.getlist('service_id[]')
            svc_titles = data.getlist('service_title[]')
            svc_descs = data.getlist('service_description[]')
            svc_icons = data.getlist('service_icon[]')

            for i, title in enumerate(svc_titles):
                if not title.strip():
                    continue
                s_id = svc_ids[i] if i < len(svc_ids) else ""
                s_desc = svc_descs[i] if i < len(svc_descs) else ""
                s_icon = svc_icons[i] if i < len(svc_icons) else ""

                if s_id.strip():
                    try:
                        svc = ClinicService.objects.get(id=s_id, clinic=clinic)
                        svc.title = title
                        svc.description = s_desc
                        svc.icon = s_icon
                        svc.order = i
                        svc.save()
                    except ClinicService.DoesNotExist:
                        pass
                else:
                    ClinicService.objects.create(clinic=clinic, title=title, description=s_desc, icon=s_icon, order=i)
            messages.success(request, gettext('Featured services updated.'))

        elif section_type == 'headers':
            fields = ['team_label', 'team_title', 'testimonials_label', 'testimonials_title']
            for field in fields:
                setattr(clinic, field, data.get(field, ''))
            messages.success(request, gettext('Section headers updated.'))

        elif section_type == 'social':
            fields = ['map_iframe_url', 'facebook', 'instagram', 'twitter', 'youtube']
            for field in fields:
                setattr(clinic, field, data.get(field, ''))
            review_url = data.get('google_review_url', '').strip()
            clinic.google_review_url = review_url if review_url.startswith('https://') else ''
            messages.success(request, gettext('Social & location info updated.'))

        clinic.save()
        return redirect('admin_clinic_setup')

    return render(request, 'clinic/admin/clinic_setup.html', {
        'clinic': clinic,
        'icon_choices': ICON_CHOICES
    })

@superadmin_required
def practitioners_list(request):
    practitioners = Practitioner.objects.all().order_by('name')
    return render(request, 'clinic/admin/practitioners_list.html', {'practitioners': practitioners})

@superadmin_required
@reject_bad_uploads
def practitioner_create(request):
    if request.method == 'POST':
        try:
            p = Practitioner(
                name=request.POST.get('name', ''),
                title=request.POST.get('title', ''),
                gender=request.POST.get('gender', ''),
                phone=request.POST.get('phone', ''),
                email=request.POST.get('email', ''),
                specialization=request.POST.get('specialization', ''),
                qualifications=request.POST.get('qualifications', ''),
                experience_years=int(request.POST.get('experience_years', 0) or 0),
                bio=request.POST.get('bio', ''),
                is_chief=request.POST.get('is_chief') == 'on',
                designation_tag=request.POST.get('designation_tag', ''),
                youtube_url=request.POST.get('youtube_url', ''),
                twitter=request.POST.get('twitter', ''),
                instagram=request.POST.get('instagram', ''),
                facebook=request.POST.get('facebook', ''),
                is_active=request.POST.get('is_active') == 'on',
            )
            if request.FILES.get('photo'):
                p.photo = checked_image(request.FILES['photo'])
            if request.POST.get('joined_date'):
                p.joined_date = request.POST['joined_date']
            p.save()
            messages.success(request, gettext('Practitioner %(name)s created.') % {'name': p.name})
            return redirect('admin_practitioners')
        except Exception as e:
            messages.error(request, gettext('Error creating practitioner: %(value1)s') % {'value1': str(e)})
    return render(request, 'clinic/admin/practitioner_form.html', {'practitioner': None})

@superadmin_required
@reject_bad_uploads
def practitioner_edit(request, pk):
    p = get_object_or_404(Practitioner, pk=pk)
    if request.method == 'POST':
        try:
            p.name = request.POST.get('name', p.name)
            p.title = request.POST.get('title', p.title)
            p.gender = request.POST.get('gender', p.gender)
            p.phone = request.POST.get('phone', p.phone)
            p.email = request.POST.get('email', p.email)
            p.specialization = request.POST.get('specialization', p.specialization)
            p.qualifications = request.POST.get('qualifications', p.qualifications)
            p.experience_years = int(request.POST.get('experience_years', p.experience_years) or 0)
            p.bio = request.POST.get('bio', p.bio)
            p.is_chief = request.POST.get('is_chief') == 'on'
            p.designation_tag = request.POST.get('designation_tag', p.designation_tag)
            p.youtube_url = request.POST.get('youtube_url', p.youtube_url)
            p.twitter = request.POST.get('twitter', p.twitter)
            p.instagram = request.POST.get('instagram', p.instagram)
            p.facebook = request.POST.get('facebook', p.facebook)
            p.is_active = request.POST.get('is_active') == 'on'
            if request.FILES.get('photo'):
                p.photo = checked_image(request.FILES['photo'])
            if request.POST.get('joined_date'):
                p.joined_date = request.POST['joined_date']
            p.save()
            messages.success(request, gettext('Practitioner %(name)s updated.') % {'name': p.name})
            return redirect('admin_practitioners')
        except Exception as e:
            messages.error(request, gettext('Error updating practitioner: %(value1)s') % {'value1': str(e)})
    return render(request, 'clinic/admin/practitioner_form.html', {'practitioner': p})

@superadmin_required
def practitioner_delete(request, pk):
    p = get_object_or_404(Practitioner, pk=pk)
    if request.method == 'POST':
        name = p.name
        p.delete()
        messages.success(request, gettext('Practitioner %(name)s deleted.') % {'name': name})
    return redirect('admin_practitioners')


# ── Testimonials CRUD ─────────────────────────────────────────────────────

@superadmin_required
def testimonials_list(request):
    """Moderation queue: filter by status, search, paginate."""
    from django.core.paginator import Paginator
    from django.db.models import Count, Q
    clinic = ClinicProfile.objects.first()
    status = request.GET.get('status', 'pending')
    statuses = dict(ClinicTestimonial.MODERATION_CHOICES)
    qs = ClinicTestimonial.objects.filter(clinic=clinic).select_related('problem') if clinic else ClinicTestimonial.objects.none()
    counts = dict(qs.values_list('moderation_status').annotate(n=Count('id')))
    if status in statuses:
        qs = qs.filter(moderation_status=status)
    else:
        status = 'all'
    q = request.GET.get('q', '').strip()[:100]
    if q:
        qs = qs.filter(Q(patient_name__icontains=q) | Q(review_text__icontains=q) | Q(patient_designation__icontains=q))
    page = Paginator(qs.order_by('display_order', '-created_at'), 24).get_page(request.GET.get('page'))
    tabs = [('all', gettext('All'), sum(counts.values()))] + [(k, label, counts.get(k, 0)) for k, label in statuses.items()]
    return render(request, 'clinic/admin/testimonials_list.html', {
        'testimonials': page, 'page_obj': page, 'clinic': clinic, 'status': status, 'q': q, 'tabs': tabs,
    })


@superadmin_required
@require_POST
def testimonial_moderate(request, pk):
    from . import stories
    t = get_object_or_404(ClinicTestimonial, pk=pk)
    error = stories.moderate(t, request.POST.get('action', ''), request.user, request.POST.get('note', '').strip())
    if error:
        messages.error(request, error)
    else:
        messages.success(request, gettext('Review updated.'))
    from spinalcure.utils import safe_next
    return redirect(safe_next(request, reverse('admin_testimonials')))


@superadmin_required
@reject_bad_uploads
def testimonial_create(request):
    clinic = ClinicProfile.objects.first()
    if not clinic:
        messages.error(request, gettext('Please set up the clinic profile first.'))
        return redirect('admin_clinic_setup')

    if request.method == 'POST':
        try:
            t = ClinicTestimonial(
                clinic=clinic,
                patient_name=request.POST.get('patient_name', '').strip(),
                patient_designation=request.POST.get('patient_designation', '').strip(),
                rating=int(request.POST.get('rating', 5)),
                review_text=request.POST.get('review_text', '').strip(),
                source=request.POST.get('source', 'internal'),
                display_order=int(request.POST.get('display_order', 0) or 0),
                is_published=request.POST.get('is_published') == 'on',
                problem_id=request.POST.get('problem') or None,
                owner_reply=request.POST.get('owner_reply', '').strip(),
                source_url=request.POST.get('source_url', '').strip(),
                posted_label=request.POST.get('posted_label', '').strip(),
            )
            if request.FILES.get('photo'):
                t.photo = checked_image(request.FILES['photo'])
            t.moderation_status = 'approved'
            t.save()
            from . import stories
            stories.log(t, 'created', request.user.get_username(), 'Published' if t.is_published else 'Saved as draft')
            messages.success(request, gettext('Testimonial from %(patient_name)s added.') % {'patient_name': t.patient_name})
            return redirect('admin_testimonials')
        except Exception as e:
            messages.error(request, gettext('Error saving testimonial: %(e)s') % {'e': e})

    return render(request, 'clinic/admin/testimonial_form.html', {
        'testimonial': None,
        'source_choices': ClinicTestimonial.SOURCE_CHOICES,
        'problems': ProblemCategory.objects.filter(is_active=True),
    })


@superadmin_required
@reject_bad_uploads
def testimonial_edit(request, pk):
    t = get_object_or_404(ClinicTestimonial, pk=pk)
    if request.method == 'POST':
        try:
            t.patient_name = request.POST.get('patient_name', t.patient_name).strip()
            t.patient_designation = request.POST.get('patient_designation', t.patient_designation).strip()
            t.rating = int(request.POST.get('rating', t.rating))
            t.review_text = request.POST.get('review_text', t.review_text).strip()
            t.source = request.POST.get('source', t.source)
            t.display_order = int(request.POST.get('display_order', t.display_order) or 0)
            was_published = t.is_published
            t.is_published = request.POST.get('is_published') == 'on'
            if t.is_published and not t.can_publish:
                t.is_published = False
                messages.warning(request, gettext('Not published: the author has not agreed, or the review was withdrawn or rejected.'))
            elif t.is_published and t.moderation_status == 'pending':
                t.moderation_status = 'approved'
            t.problem_id = request.POST.get('problem') or None
            t.owner_reply = request.POST.get('owner_reply', '').strip()
            t.source_url = request.POST.get('source_url', '').strip()
            t.posted_label = request.POST.get('posted_label', '').strip()
            if request.FILES.get('photo'):
                t.photo = checked_image(request.FILES['photo'])
            t.save()
            from . import stories
            stories.log(t, 'edited', request.user.get_username(),
                        '' if was_published == t.is_published else ('Published' if t.is_published else 'Unpublished'))
            messages.success(request, gettext('Testimonial from %(patient_name)s updated.') % {'patient_name': t.patient_name})
            return redirect('admin_testimonials')
        except Exception as e:
            messages.error(request, gettext('Error updating testimonial: %(e)s') % {'e': e})

    return render(request, 'clinic/admin/testimonial_form.html', {
        'testimonial': t, 'history': t.moderation_history.all()[:50],
        'source_choices': ClinicTestimonial.SOURCE_CHOICES,
        'problems': ProblemCategory.objects.filter(is_active=True),
    })


@superadmin_required
def testimonial_delete(request, pk):
    t = get_object_or_404(ClinicTestimonial, pk=pk)
    if request.method == 'POST':
        name = t.patient_name
        from . import stories
        stories.log(t, 'deleted', request.user.get_username(), f'{name[:60]} ({t.rating}*)')
        t.delete()
        messages.success(request, gettext('Testimonial from %(name)s deleted.') % {'name': name})
    return redirect('admin_testimonials')


@superadmin_required
@require_POST
def testimonial_toggle_publish(request, pk):
    """Quick AJAX toggle for published status (POST only: a GET must never change data)."""
    from django.http import JsonResponse
    from . import stories
    t = get_object_or_404(ClinicTestimonial, pk=pk)
    error = stories.moderate(t, 'unpublish' if t.is_published else 'publish', request.user)
    if error:
        return JsonResponse({'status': 'error', 'message': error, 'is_published': t.is_published}, status=400)
    return JsonResponse({'status': 'ok', 'is_published': t.is_published})


@superadmin_required
@require_POST
def revert_audit_log_view(request, pk):
    """Revert an action recorded in the AuditLog."""
    import json
    import logging
    from django.core import serializers
    from django.apps import apps
    from django.http import JsonResponse
    from clinic.models import AuditLog
    
    logger = logging.getLogger(__name__)
    # Reverting re-creates or overwrites records from a snapshot: super admins only.
    if not (request.user.is_superuser or getattr(request.user, 'role', '') == 'superadmin'):
        return JsonResponse({'status': 'error', 'message': gettext('Permission denied.')}, status=403)
    log = get_object_or_404(AuditLog, pk=pk)
    
    if log.reverted:
        return JsonResponse({'status': 'error', 'message': gettext('Already reverted.')}, status=400)
        
    try:
        if log.action == 'delete' and log.snapshot:
            # Recreate the object from snapshot
            for obj in serializers.deserialize('json', json.dumps([log.snapshot])):
                obj.save(force_insert=True)
                
        elif log.action == 'update' and log.raw_changes:
            # Revert the specific fields
            model_class = None
            for model in apps.get_models():
                if model.__name__ == log.model_name:
                    model_class = model
                    break
                    
            if not model_class:
                return JsonResponse({'status': 'error', 'message': gettext('Model %(model_name)s not found.') % {'model_name': log.model_name}}, status=400)
                
            obj = model_class.objects.get(pk=log.object_id)
            for field_name, old_val in log.raw_changes.items():
                setattr(obj, field_name, old_val)
            obj.save()
            
        else:
            return JsonResponse({'status': 'error', 'message': gettext('This action cannot be reverted automatically (missing raw data).')}, status=400)
            
        log.reverted = True
        log.save(update_fields=['reverted'])
        
        from spinalcure.utils import log_action
        log_action(request, 'update', log.model_name, f"[REVERTED] {log.object_repr}", object_id=log.object_id, changes={'Revert': {'old': log.action, 'new': 'Reverted'}})
        
        return JsonResponse({'status': 'success', 'message': gettext('Action successfully reverted.')})
    except Exception as e:
        logger.error(f'Error reverting log {pk}: {e}')
        return JsonResponse({'status': 'error', 'message': gettext('Error reverting: %(value1)s') % {'value1': str(e)}}, status=500)
@superadmin_required
def activity_log_view(request):
    """View the full CRUD activity log — superadmin only."""
    from .models import AuditLog
    from accounts.models import CustomUser
    from django.core.paginator import Paginator

    # Filters
    action_filter = request.GET.get('action', '')
    module_filter = request.GET.get('module', '')
    user_filter = request.GET.get('user', '')

    logs = AuditLog.objects.select_related('user').order_by('-created_at')

    if action_filter:
        logs = logs.filter(action=action_filter)
    if module_filter:
        logs = logs.filter(model_name=module_filter)
    if user_filter:
        logs = logs.filter(user__id=user_filter)

    paginator = Paginator(logs, 50)
    page_obj = paginator.get_page(request.GET.get('page'))

    # Distinct modules for filter dropdown
    modules = AuditLog.objects.values_list('model_name', flat=True).distinct().order_by('model_name')
    staff_users = CustomUser.objects.filter(is_staff=True).order_by('first_name', 'email')

    context = {
        'logs': page_obj,
        'action_filter': action_filter,
        'module_filter': module_filter,
        'user_filter': user_filter,
        'modules': modules,
        'staff_users': staff_users,
        'total_count': AuditLog.objects.count(),
    }
    return render(request, 'clinic/admin/activity_log.html', context)
