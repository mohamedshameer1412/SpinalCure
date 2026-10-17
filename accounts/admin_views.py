from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from spinalcure.decorators import superadmin_required
from .models import CustomUser

@superadmin_required
def users_list(request):
    users = CustomUser.objects.all().order_by('-date_joined')
    return render(request, 'accounts/admin/users_list.html', {'users': users})

@superadmin_required
def user_create(request):
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        first_name = request.POST.get('first_name', '')
        last_name = request.POST.get('last_name', '')
        password = request.POST.get('password', '')
        role = request.POST.get('role', 'receptionist')
        is_staff = request.POST.get('is_staff') == 'on'

        if CustomUser.objects.filter(username=username).exists():
            messages.error(request, f'Username "{username}" is already taken.')
        elif not password:
            messages.error(request, 'Password is required.')
        else:
            try:
                user = CustomUser.objects.create_user(
                    username=username,
                    email=email,
                    password=password,
                    first_name=first_name,
                    last_name=last_name,
                    is_staff=is_staff,
                )
                if hasattr(user, 'role'):
                    user.role = role
                    user.save()
                messages.success(request, f'User "{username}" created successfully.')
                return redirect('admin_users')
            except Exception as e:
                messages.error(request, f'Error creating user: {str(e)}')

    return render(request, 'accounts/admin/user_form.html', {'edit_user': None})

@superadmin_required
def user_edit(request, pk):
    edit_user = get_object_or_404(CustomUser, pk=pk)
    if request.method == 'POST':
        try:
            edit_user.first_name = request.POST.get('first_name', edit_user.first_name)
            edit_user.last_name = request.POST.get('last_name', edit_user.last_name)
            edit_user.email = request.POST.get('email', edit_user.email)
            edit_user.is_staff = request.POST.get('is_staff') == 'on'
            new_password = request.POST.get('password', '')
            if new_password:
                edit_user.set_password(new_password)
            if hasattr(edit_user, 'role'):
                edit_user.role = request.POST.get('role', edit_user.role)
            edit_user.save()
            messages.success(request, f'User "{edit_user.username}" updated.')
            return redirect('admin_users')
        except Exception as e:
            messages.error(request, f'Error updating user: {str(e)}')
    return render(request, 'accounts/admin/user_form.html', {'edit_user': edit_user})

@superadmin_required
def user_toggle_active(request, pk):
    user = get_object_or_404(CustomUser, pk=pk)
    if user == request.user:
        messages.error(request, 'You cannot deactivate your own account.')
    else:
        user.is_active = not user.is_active
        user.save()
        status = 'activated' if user.is_active else 'deactivated'
        messages.success(request, f'User "{user.username}" has been {status}.')
    return redirect('admin_users')
