from django.contrib import messages
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST

from spinalcure.decorators import role_required
from spinalcure.utils import log_action
from . import roles
from .models import CustomUser


def _role_options(actor):
    allowed = set(roles.assignable_roles(actor))
    return [(code, label) for code, label in roles.ROLE_CHOICES if code in allowed]


def _apply_password(user, password, errors):
    try:
        validate_password(password, user)
    except ValidationError as e:
        errors.extend(e.messages)
        return
    user.set_password(password)


@role_required('users_manage')
def users_list(request):
    users = list(CustomUser.objects.all().order_by('-date_joined'))
    manageable_ids = {u.pk for u in users if roles.can_manage_user(request.user, u)}
    return render(request, 'accounts/admin/users_list.html', {'users': users, 'manageable_ids': manageable_ids})


@role_required('users_manage')
def user_create(request):
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        role = request.POST.get('role', roles.RECEPTIONIST)
        errors = []
        if not username:
            errors.append('Username is required.')
        elif CustomUser.objects.filter(username__iexact=username).exists():
            errors.append(f'Username "{username}" is already taken.')
        if email and CustomUser.objects.filter(email__iexact=email).exists():
            errors.append('A user with this email already exists.')
        if role not in roles.assignable_roles(request.user):
            errors.append('You are not allowed to assign that role.')
        user = CustomUser(
            username=username, email=email, role=role,
            first_name=request.POST.get('first_name', '').strip(),
            last_name=request.POST.get('last_name', '').strip(),
        )
        password = request.POST.get('password', '')
        if not password:
            errors.append('Password is required.')
        else:
            _apply_password(user, password, errors)
        if not errors:
            with transaction.atomic():
                user.save()
            log_action(request, 'create', 'User', f'{username} ({user.get_role_display()})', object_id=user.pk)
            from django.conf import settings
            from django.urls import reverse
            from notifications.services import notify_users
            # Never email the password; the user signs in with the one given in person or uses "Forgot password".
            notify_users([user], 'staff_invited', f'Welcome to {settings.SITE_NAME}',
                         f'An account was created for you as {user.get_role_display()}. Sign in with your email address. '
                         'If you were not given a password, use "Forgot password" on the sign-in page.',
                         reverse('login'), dedupe_key=f'invite:{user.pk}')
            messages.success(request, f'User "{username}" created successfully.')
            return redirect('admin_users')
        for e in errors:
            messages.error(request, e)

    return render(request, 'accounts/admin/user_form.html', {'edit_user': None, 'role_options': _role_options(request.user)})


@role_required('users_manage')
def user_edit(request, pk):
    edit_user = get_object_or_404(CustomUser, pk=pk)
    if not roles.can_manage_user(request.user, edit_user):
        messages.error(request, 'You cannot edit a user at or above your own role.')
        return redirect('admin_users')
    if request.method == 'POST':
        errors = []
        old_role = edit_user.role
        role = request.POST.get('role', edit_user.role)
        if role not in roles.assignable_roles(request.user):
            errors.append('You are not allowed to assign that role.')
        email = request.POST.get('email', edit_user.email).strip()
        if email and CustomUser.objects.filter(email__iexact=email).exclude(pk=edit_user.pk).exists():
            errors.append('A user with this email already exists.')
        edit_user.first_name = request.POST.get('first_name', edit_user.first_name).strip()
        edit_user.last_name = request.POST.get('last_name', edit_user.last_name).strip()
        edit_user.email = email
        edit_user.role = role
        new_password = request.POST.get('password', '')
        if new_password:
            _apply_password(edit_user, new_password, errors)
        if not errors:
            edit_user.save()
            changes = {'role': {'old': old_role, 'new': role}} if old_role != role else None
            log_action(request, 'update', 'User', edit_user.username, object_id=edit_user.pk, changes=changes)
            messages.success(request, f'User "{edit_user.username}" updated.')
            return redirect('admin_users')
        for e in errors:
            messages.error(request, e)
    return render(request, 'accounts/admin/user_form.html', {'edit_user': edit_user, 'role_options': _role_options(request.user)})


@require_POST
@role_required('users_manage')
def user_toggle_active(request, pk):
    user = get_object_or_404(CustomUser, pk=pk)
    if not roles.can_manage_user(request.user, user):
        messages.error(request, 'You cannot change the status of this user.')
    else:
        user.is_active = not user.is_active
        user.save(update_fields=['is_active'])
        status = 'activated' if user.is_active else 'deactivated'
        log_action(request, 'update', 'User', f'{user.username} {status}', object_id=user.pk)
        messages.success(request, f'User "{user.username}" has been {status}.')
    return redirect('admin_users')
