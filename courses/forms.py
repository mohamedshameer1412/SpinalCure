from django import forms
from .models import Course, CourseBatch


class CourseForm(forms.ModelForm):
    class Meta:
        model = Course
        fields = [
            'title', 'short_description', 'description', 'outcomes',
            'course_content', 'platform', 'fees', 'original_fees', 'duration',
            'image', 'is_published', 'clinic'
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': 'premium-input', 'placeholder': 'e.g. Basic Acupuncture Certification'}),
            'short_description': forms.TextInput(attrs={'class': 'premium-input', 'placeholder': 'Brief summary for cards...'}),
            'description': forms.Textarea(attrs={'class': 'premium-textarea', 'rows': 4, 'placeholder': 'Detailed course overview...'}),
            'outcomes': forms.Textarea(attrs={'class': 'premium-textarea', 'rows': 5, 'placeholder': 'One outcome per line...'}),
            'course_content': forms.Textarea(attrs={'class': 'premium-textarea', 'rows': 6, 'placeholder': 'Course syllabus/topics...'}),
            'platform': forms.Select(attrs={'class': 'premium-select'}),
            'fees': forms.NumberInput(attrs={'class': 'premium-input', 'placeholder': '0.00'}),
            'original_fees': forms.NumberInput(attrs={'class': 'premium-input', 'placeholder': '0.00'}),
            'duration': forms.TextInput(attrs={'class': 'premium-input', 'placeholder': 'e.g. 12 Weeks'}),
            'clinic': forms.Select(attrs={'class': 'premium-select'}),
            'image': forms.FileInput(attrs={'class': 'premium-file-input'}),
        }


class CourseBatchForm(forms.ModelForm):
    class Meta:
        model = CourseBatch
        fields = [
            'name', 'start_date', 'end_date', 'schedule_details',
            'max_participants', 'is_active', 'feedback_enabled', 'is_published'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'premium-input', 'placeholder': 'e.g. Summer Intake 2025'}),
            'start_date': forms.DateInput(attrs={'class': 'premium-input', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'premium-input', 'type': 'date'}),
            'schedule_details': forms.Textarea(attrs={'class': 'premium-textarea', 'rows': 3, 'placeholder': 'e.g. Saturday & Sunday, 10am - 1pm'}),
            'max_participants': forms.NumberInput(attrs={'class': 'premium-input', 'placeholder': 'Leave blank for unlimited'}),
        }
