from django import forms
from django.utils.translation import gettext_lazy as _

from apps.users.models import StaffUser, Department
from apps.courses.models import Category, Course, Module, Lesson, Enrollment, TrainingSession
from apps.courses.storage import MAX_UPLOAD_BYTES, MAX_VIDEO_BYTES


def apply_labels(form, labels):
    """Set translated labels/help text on a form in one place.

    Model-derived labels are plain English strings baked in at import time, so they
    ignore the active language. gettext_lazy defers translation to render time.
    """
    for name, label in labels.items():
        if name in form.fields:
            form.fields[name].label = label
    return form


class CreateUserForm(forms.ModelForm):
    """Provisions an HR / HOD / staff account (super admin only)."""

    password = forms.CharField(
        label="Temporary password",
        required=False,
        widget=forms.PasswordInput(attrs={'class': 'form-input', 'autocomplete': 'new-password'}),
        help_text=_("Temporary password. Leave blank to auto-generate a random one."),
    )

    class Meta:
        model = StaffUser
        fields = ['employee_id', 'first_name', 'last_name', 'email', 'department',
                  'designation', 'role']
        widgets = {
            'employee_id': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. HR001'}),
            'first_name': forms.TextInput(attrs={'class': 'form-input'}),
            'last_name': forms.TextInput(attrs={'class': 'form-input'}),
            'email': forms.EmailInput(attrs={'class': 'form-input'}),
            'department': forms.Select(attrs={'class': 'form-input'}),
            'designation': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. HR Manager'}),
            'role': forms.Select(attrs={'class': 'form-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['department'].empty_label = _("No department")
        self.fields['employee_id'].help_text = _("Uppercase letters/numbers only (e.g. HR001).")
        self.fields['employee_id'].widget.attrs['autofocus'] = True

    def clean_employee_id(self):
        employee_id = self.cleaned_data['employee_id'].strip().upper()
        if StaffUser.objects.filter(employee_id=employee_id).exists():
            raise forms.ValidationError(_("An account with this Employee ID already exists."))
        return employee_id

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip()
        if email and StaffUser.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(_("An account with this email already exists."))
        return email


class CourseForm(forms.ModelForm):
    class Meta:
        model = Course
        fields = ['title', 'title_hi', 'description', 'description_hi', 'category', 'is_mandatory', 'target_departments']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. Laboratory Safety & Handling'}),
            'title_hi': forms.TextInput(attrs={'class': 'form-input'}),
            'description': forms.Textarea(attrs={'class': 'form-input', 'rows': 3}),
            'description_hi': forms.Textarea(attrs={'class': 'form-input', 'rows': 3}),
            'category': forms.Select(attrs={'class': 'form-input'}),
            'is_mandatory': forms.CheckboxInput(attrs={'class': 'form-check'}),
            'target_departments': forms.SelectMultiple(attrs={'class': 'form-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Model-derived labels arrive in English ("Title hi", "Description hi") and
        # are not translated, so the content screens stayed half-English in Hindi
        # mode - exactly where an HOD does their work. gettext_lazy resolves per
        # request, so one declaration covers every form below.
        apply_labels(self, {
            'title': _("Title"),
            'title_hi': _("Title (Hindi)"),
            'description': _("Description"),
            'description_hi': _("Description (Hindi)"),
            'category': _("Category"),
            'is_mandatory': _("Mandatory for all staff"),
            'target_departments': _("Restrict to departments"),
        })
        self.fields['category'].empty_label = _("Select category")
        if self.instance and self.instance.pk:
            self.fields['target_departments'].help_text = _("Leave empty to make this course available to all departments.")


class ModuleForm(forms.ModelForm):
    class Meta:
        model = Module
        fields = ['title', 'title_hi', 'order']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. Module 1: Introduction'}),
            'title_hi': forms.TextInput(attrs={'class': 'form-input'}),
            'order': forms.NumberInput(attrs={'class': 'form-input', 'min': 1}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_labels(self, {
            'title': _("Title"),
            'title_hi': _("Title (Hindi)"),
            'order': _("Order"),
        })


class LessonForm(forms.ModelForm):
    class Meta:
        model = Lesson
        fields = ['title', 'title_hi', 'lesson_type', 'video_file', 'video_url', 'pdf_file', 'sop_text', 'duration_minutes', 'order']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. Personal Protective Equipment'}),
            'title_hi': forms.TextInput(attrs={'class': 'form-input'}),
            'lesson_type': forms.Select(attrs={'class': 'form-input'}),
            'video_file': forms.ClearableFileInput(attrs={'class': 'form-input'}),
            'video_url': forms.URLInput(attrs={'class': 'form-input'}),
            'pdf_file': forms.ClearableFileInput(attrs={'class': 'form-input'}),
            'sop_text': forms.Textarea(attrs={'class': 'form-input', 'rows': 4}),
            'duration_minutes': forms.NumberInput(attrs={'class': 'form-input', 'min': 1}),
            'order': forms.NumberInput(attrs={'class': 'form-input', 'min': 1}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_labels(self, {
            'title': _("Title"),
            'title_hi': _("Title (Hindi)"),
            'lesson_type': _("Lesson type"),
            'video_file': _("Upload video"),
            'video_url': _("Video link"),
            'pdf_file': _("SOP PDF"),
            'sop_text': _("SOP text"),
            'duration_minutes': _("Duration (minutes)"),
            'order': _("Order"),
        })
        self.fields['lesson_type'].empty_label = _("Select lesson type")
        self.fields['title_hi'].help_text = _("Leave blank to fall back to the English title.")
        self.fields['video_file'].help_text = _(
            "Stored in the database, so it survives a redeploy. Max {limit} MB."
        ).format(limit=MAX_VIDEO_BYTES // (1024 * 1024))
        self.fields['video_url'].help_text = _(
            "YouTube, Vimeo, or a direct link to an .mp4 / .webm / .m3u8 file. "
            "YouTube and Vimeo links play in an embedded player."
        )
        self.fields['sop_text'].help_text = _("Used to generate AI quiz questions from this SOP.")
        self.fields['pdf_file'].help_text = _(
            "Stored in the database, so it survives a redeploy. Max {limit} MB, PDF only."
        ).format(limit=MAX_UPLOAD_BYTES // (1024 * 1024))

    def clean_pdf_file(self):
        pdf = self.cleaned_data.get('pdf_file')
        if not pdf:
            return pdf
        name = (getattr(pdf, 'name', '') or '').lower()
        if name and not name.endswith('.pdf'):
            raise forms.ValidationError(_("Only PDF files can be uploaded here."))
        size = getattr(pdf, 'size', None)
        if size is not None and size > MAX_UPLOAD_BYTES:
            raise forms.ValidationError(
                _("That file is too large. Maximum size is {limit} MB.").format(
                    limit=MAX_UPLOAD_BYTES // (1024 * 1024))
            )
        if size == 0:
            raise forms.ValidationError(_("The uploaded file is empty."))
        return pdf

    def clean_video_file(self):
        vid = self.cleaned_data.get('video_file')
        if not vid:
            return vid
        name = (getattr(vid, 'name', '') or '').lower()
        if name and not name.endswith(('.mp4', '.webm', '.mov', '.m4v', '.ogv', '.ogg')):
            raise forms.ValidationError(_("Upload an MP4 or WebM video."))
        size = getattr(vid, 'size', None)
        if size is not None and size > MAX_VIDEO_BYTES:
            raise forms.ValidationError(
                _("That file is too large. Maximum size is {limit} MB.").format(
                    limit=MAX_VIDEO_BYTES // (1024 * 1024))
            )
        return vid

    def clean(self):
        cleaned = super().clean()
        lesson_type = cleaned.get('lesson_type')
        video_url = cleaned.get('video_url', '')
        sop_text = cleaned.get('sop_text', '')
        existing_pdf = getattr(self.instance, 'pdf_file', None)
        existing_video = getattr(self.instance, 'video_file', None)
        if lesson_type == 'video' and not (video_url or self.cleaned_data.get('video_file') or existing_video):
            self.add_error('video_url', _("Upload a video or paste a video link for video lessons."))
        if lesson_type == 'pdf' and not (self.cleaned_data.get('pdf_file') or sop_text or existing_pdf):
            self.add_error('pdf_file', _("Upload a PDF or paste the SOP text for SOP PDF lessons."))
        return cleaned


class EnrollForm(forms.Form):
    course = forms.ModelChoiceField(
        queryset=Course.objects.all().order_by('title'),
        label=_("Course"),
        widget=forms.Select(attrs={'class': 'form-input'}),
    )
    department = forms.ModelChoiceField(
        queryset=Department.objects.all().order_by('name'),
        label=_("Department"),
        required=False,
        empty_label=_("All departments (all active staff)"),
        widget=forms.Select(attrs={'class': 'form-input'}),
    )


class AssignStaffForm(forms.Form):
    staff_user = forms.ModelChoiceField(
        queryset=StaffUser.objects.filter(is_active=True).order_by('employee_id'),
        label=_("Employee"),
        widget=forms.Select(attrs={'class': 'form-input'}),
    )
    course = forms.ModelChoiceField(
        queryset=Course.objects.all().order_by('title'),
        label=_("Course"),
        widget=forms.Select(attrs={'class': 'form-input'}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ('staff_user', 'course'):
            self.fields[name].empty_label = _("Choose ...")


class TrainingSessionForm(forms.ModelForm):
    class Meta:
        model = TrainingSession
        fields = ['title', 'description', 'course', 'date', 'start_time', 'end_time', 'location', 'is_mandatory']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. Fire Drill Workshop'}),
            'description': forms.Textarea(attrs={'class': 'form-input', 'rows': 3}),
            'course': forms.Select(attrs={'class': 'form-input'}),
            'date': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
            'start_time': forms.TimeInput(attrs={'class': 'form-input', 'type': 'time'}),
            'end_time': forms.TimeInput(attrs={'class': 'form-input', 'type': 'time'}),
            'location': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. Training Hall, Block B'}),
            'is_mandatory': forms.CheckboxInput(attrs={'class': 'form-check'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['course'].empty_label = _("No linked course (optional)")
