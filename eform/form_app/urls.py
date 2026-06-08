from django.urls import path 
from . import views

urlpatterns = [
    path('admin/forms/<int:form_id>/design/', views.admin_form_design_view, name='admin_builder_form'),
    path('api/upload-file/', views.upload_file_to_minio, name='upload_file'),
    path('', views.home_view, name='home'),
    path('forms/', views.list_forms_view, name='list_forms'),
    path('forms/<int:form_id>/', views.render_form_view, name='render_form'),
    
    path('submissions/', views.list_submitted_forms_views, name='list_submissions'),
    path('submissions/<int:submission_id>/detail/', views.detail_submit_form_view, name='detail_submit_form'),
    path('forms/<int:form_id>/submit/', views.submit_form_api, name='submit_form_api'),
    
]
