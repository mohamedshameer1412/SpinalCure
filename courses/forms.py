from django import forms
from .models import Course, CourseBatch, Student


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
            'max_participants', 'is_active', 'feedback_enabled', 'is_published', 'min_attendance_percent'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'premium-input', 'placeholder': 'e.g. Summer Intake 2025'}),
            'start_date': forms.DateInput(attrs={'class': 'premium-input', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'premium-input', 'type': 'date'}),
            'schedule_details': forms.Textarea(attrs={'class': 'premium-textarea', 'rows': 3, 'placeholder': 'e.g. Saturday & Sunday, 10am - 1pm'}),
            'max_participants': forms.NumberInput(attrs={'class': 'premium-input', 'placeholder': 'Leave blank for unlimited'}),
        }


class StudentProfileForm(forms.ModelForm):
    """What a confirmed student adds after registering. Photo, designation and address make the ID card; email is
    required only when none was given at registration."""

    class Meta:
        model = Student
        fields = ['photo', 'email', 'designation', 'organisation', 'address', 'date_of_birth', 'gender', 'blood_group',
                  'emergency_contact_name', 'emergency_contact_phone']
        widgets = {'address': forms.Textarea(attrs={'rows': 3}), 'date_of_birth': forms.DateInput(attrs={'type': 'date'})}

    PRIVATE = ('email', 'address', 'date_of_birth', 'emergency_contact_name', 'emergency_contact_phone')

    def __init__(self, *args, staff=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.staff = staff
        for name, field in self.fields.items():
            field.widget.attrs.setdefault('class', 'w-full')
        self.fields['photo'].widget.attrs.pop('class', None)
        self.fields['photo'].widget.attrs['accept'] = 'image/*'
        if staff:
            for f in ('photo', 'designation', 'address', 'email'):
                self.fields[f].required = False
            return
        # The private link is not a login: it never shows stored personal details back. A blank field keeps what is on file,
        # and a detail is only required while none is stored.
        for f in self.PRIVATE:
            if getattr(self.instance, f):
                self.initial[f] = ''
        self.fields['photo'].required = not self.instance.photo
        for f in ('designation', 'address', 'email'):
            self.fields[f].required = not getattr(self.instance, f)

    def clean(self):
        data = super().clean()
        if not self.staff:
            for f in self.PRIVATE:
                if not data.get(f) and getattr(self.instance, f):
                    data[f] = getattr(self.instance, f)
        return data

    def clean_emergency_contact_phone(self):
        from spinalcure.validators import validate_phone_number
        value = self.cleaned_data.get('emergency_contact_phone', '').strip()
        if value:
            validate_phone_number(value)
        return value
