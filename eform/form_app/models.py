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
    
from django.contrib.auth.models import User

class FormSubmission(models.Model):
    STATUS_CHOICES = [
        ('pending_checker', 'Chờ Checker duyệt'),
        ('pending_manager', 'Chờ Manager duyệt'),
        ('approved', 'Đã phê duyệt'),
        ('rejected', 'Bị từ chối'),
        ('cancelled', 'Đã hủy (Lúc chưa duyệt)'),
        ('pending_cancel_checker', 'Xin hủy - Chờ Checker'),
        ('pending_cancel_manager', 'Xin hủy - Chờ Manager'),
        ('revoked', 'Tài liệu đã hủy'),
    ]
    form_definition = models.ForeignKey(
        FormDefinition,
        on_delete=models.CASCADE,
    )
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='submissions'
    )
    data = models.JSONField()
    submitted_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=50,
        choices=STATUS_CHOICES,
        default='pending_checker'
    )
    
    # Thông tin kiểm duyệt (Checker - Cấp 1)
    checked_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='checked_submissions'
    )
    checked_at = models.DateTimeField(null=True, blank=True)
    
    # Thông tin phê duyệt (Manager - Cấp 2)
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_submissions'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    
    # Ý kiến phản hồi của người duyệt
    checker_comment = models.TextField(blank=True, default='')
    manager_comment = models.TextField(blank=True, default='')


    
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