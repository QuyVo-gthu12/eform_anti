from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from .models import FormDefinition, FormSubmission

@admin.register(FormDefinition)
class FormDefinitionAdmin(admin.ModelAdmin):
    list_display = ('title', 'design_form', 'is_active', 'created_at', 'updated_at')
    list_filter = ('is_active',)
    search_fields = ('title',)
    
    def design_form(self, obj):
        if obj.id:
            url = reverse('admin_builder_form', args=[obj.id])
            return format_html(
                '<a class="button" href="{}" '
                'style="background: #10b981; color: white; padding: 6px 14px; border-radius: 6px; font-weight: 600; display: inline-block; text-decoration: none; border: none; font-size: 13px; box-shadow: 0 2px 4px rgba(16,185,129,0.2); transition: all 0.2s;"> '
                '🎨 Thiết kế Form</a>', url
            )
        return "-"
    
    design_form.short_description = "thiet ke"
    