from django.db import models

class FormDefinition(models.Model):
    title = models.CharField(max_length=50, unique=True)

    description = models.TextField(
        blank=True,
        null=True
    )

    schema_json = models.JSONField()

    is_active = models.BooleanField(
        default=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    def __str__(self):
        return self.title
    
class FormSubmission(models.Model):
    STATUS_CHOICES = [
        ('submitted', 'Đã nộp'),
        ('cancelled', 'Đã hủy'),
    ]
    form_definition = models.ForeignKey(
        FormDefinition,
        on_delete=models.CASCADE,
    )
    data = models.JSONField()
    submitted_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='submitted'
    )

    
class FormDraft(models.Model):
    form_definition = models.ForeignKey(
        FormDefinition,
        on_delete=models.CASCADE,
        related_name='drafts'
    )
    title = models.CharField(max_length=200, blank=True, default='')
    data = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"Nháp: {self.title or 'Chưa đặt tên'} ({self.form_definition.title})"