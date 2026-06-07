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
    form_definition = models.ForeignKey(
        FormDefinition,
        on_delete=models.CASCADE,
    )
    data = models.JSONField()
    submitted_at = models.DateTimeField(auto_now_add=True)