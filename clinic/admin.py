from django.contrib import admin
from .models import ClinicProfile, Practitioner
from .blog_models import BlogPost, BlogTag


@admin.register(ClinicProfile)
class ClinicProfileAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone', 'email')


@admin.register(Practitioner)
class PractitionerAdmin(admin.ModelAdmin):
    list_display = ('name', 'title', 'specialization', 'is_active')
    list_filter = ('is_active', 'gender')
    search_fields = ('name', 'specialization')


@admin.register(BlogPost)
class BlogPostAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'status', 'published_at', 'read_time_minutes')
    list_filter = ('status', 'tags')
    search_fields = ('title', 'excerpt')
    prepopulated_fields = {'slug': ('title',)}
    date_hierarchy = 'published_at'


@admin.register(BlogTag)
class BlogTagAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}
