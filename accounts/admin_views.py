from django.utils.translation import gettext
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from spinalcure.rbac import require_capability
from spinalcure.utils import log_action
from .forms import UserAdminForm
from .models import CustomUser


@require_capability('users.manage')
def users_list(request):
    users = CustomUser.objects.select_related('staff_profile').order_by('-date_joined')
    return render(request, 'accounts/admin/users_list.html', {'users': users})


@require_capability('users.manage')
def user_create(request):
    form = UserAdminForm(request.POST or None, request.FILES or None, actor=request.user)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        log_action(request, 'create', 'User', f'{user.username} ({user.get_role_display()})', object_id=user.pk)
        messages.success(request, gettext('User "%(username)s" created successfully.') % {'username': user.username})
        return redirect('admin_users')
    return render(request, 'accounts/admin/user_form.html', {'edit_user': None, 'form': form})


@require_capability('users.manage')
def user_edit(request, pk):
    edit_user = get_object_or_404(CustomUser, pk=pk)
    if edit_user.is_superuser and not request.user.is_superuser:
        messages.error(request, gettext('Only a super admin can edit a super admin.'))
        return redirect('admin_users')
    form = UserAdminForm(request.POST or None, request.FILES or None, instance=edit_user, actor=request.user)
    if request.method == 'POST' and form.is_valid():
        old_role = CustomUser.objects.get(pk=pk).role
        user = form.save()
        log_action(request, 'update', 'User', user.username, object_id=user.pk,
                   changes={'role': {'old': old_role, 'new': user.role}} if old_role != user.role else None)
        messages.success(request, gettext('User "%(username)s" updated.') % {'username': user.username})
        return redirect('admin_users')
    return render(request, 'accounts/admin/user_form.html', {'edit_user': edit_user, 'form': form})


@require_POST
@require_capability('users.manage')
def user_toggle_active(request, pk):
    user = get_object_or_404(CustomUser, pk=pk)
    if user == request.user:
        messages.error(request, gettext('You cannot deactivate your own account.'))
    elif user.is_superuser and not request.user.is_superuser:
        messages.error(request, gettext('Only a super admin can change a super admin.'))
    else:
        user.is_active = not user.is_active
        user.save(update_fields=['is_active'])
        log_action(request, 'update', 'User', user.username, object_id=user.pk,
                   changes={'is_active': {'old': not user.is_active, 'new': user.is_active}})
        messages.success(request, gettext('User "%(username)s" has been %(value3)s.') % {'username': user.username, 'value3': "activated" if user.is_active else "deactivated"})
    return redirect('admin_users')
