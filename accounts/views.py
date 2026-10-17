from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import CustomUser

@login_required
def settings_view(request):
    user = request.user
    if request.method == 'POST':
        # Simple update logic for simulation
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        email = request.POST.get('email')
        phone = request.POST.get('phone')
        bio = request.POST.get('bio')
        
        user.first_name = first_name
        user.last_name = last_name
        user.email = email
        user.phone = phone
        user.bio = bio
        user.save()
        messages.success(request, 'Profile updated successfully!')
        return redirect('settings')
        
    return render(request, 'accounts/settings.html', {'user': user})
