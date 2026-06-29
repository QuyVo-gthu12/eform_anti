from django.urls import path 
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('admin/forms/<int:form_id>/design/', views.admin_form_design_view, name='admin_builder_form'),
    path('api/upload-file/', views.upload_file_to_minio, name='upload_file'),
    path('', views.home_view, name='home'),
    path('forms/', views.list_forms_view, name='list_forms'),
    
    # Class-Based Views
    path('forms/<int:form_id>/', views.RenderFormView.as_view(), name='render_form'),
    path('drafts/', views.ListDraftsPageView.as_view(), name='list_drafts'),
    path('forms/<int:form_id>/submit/', views.SubmitFormApiView.as_view(), name='submit_form_api'),
    
    # Draft APIs (Class-Based Views)
    path('api/forms/<int:form_id>/drafts/save/', views.SaveDraftApiView.as_view(), name='save_draft_api'),
    path('api/forms/<int:form_id>/drafts/', views.ListDraftsApiView.as_view(), name='list_drafts_api'),
    path('api/forms/<int:form_id>/drafts/<int:draft_id>/', views.LoadDraftApiView.as_view(), name='load_draft_api'),
    path('api/forms/<int:form_id>/drafts/<int:draft_id>/delete/', views.DeleteDraftApiView.as_view(), name='delete_draft_api'),
    
    # Submissions
    path('submissions/', views.list_submitted_forms_views, name='list_submissions'),
    path('submissions/<int:submission_id>/detail/', views.detail_submit_form_view, name='detail_submit_form'),
    path('submissions/<int:submission_id>/cancel/', views.CancelSubmissionView.as_view(), name='cancel_submission'),
    path('submissions/<int:submission_id>/request-revoke/', views.RequestRevokeApiView.as_view(), name='request_revoke'),
    
    # Public Approved Forms
    path('public-approved/', views.PublicApprovedFormsView.as_view(), name='public_approved_list'),
    
    # Approval flow (RBAC)
    path('approvals/', views.ApproveListView.as_view(), name='approve_list'),
    path('submissions/<int:submission_id>/approve/', views.ApproveSubmissionView.as_view(), name='approve_submission'),
    
    # Auth
    path('login/', auth_views.LoginView.as_view(template_name='form_app/user/login.html', next_page='home', redirect_authenticated_user=True), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
]
