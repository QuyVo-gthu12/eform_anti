from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render, get_object_or_404, redirect
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.views import View
from .models import FormDefinition, FormSubmission, FormDraft
import json
import uuid
import os
from django.conf import settings
from django.http import JsonResponse, HttpResponseForbidden
from .minio_client import get_minio_client
from datetime import timedelta
from django.utils import timezone
from django.core.mail import send_mail
import threading

def send_email_async(subject, message, recipient_list):
    def send():
        try:
            send_mail(
                subject,
                message,
                settings.EMAIL_HOST_USER,
                recipient_list,
                fail_silently=True,
            )
        except Exception as e:
            print(f"Lỗi gửi email: {e}")
    threading.Thread(target=send).start()


def home_view(request):
    return render(request, "form_app/user/home.html")

def list_forms_view(request):
    # Lấy các form đang active từ database
    forms = FormDefinition.objects.filter(is_active=True).order_by('-created_at')
    return render(request, 'form_app/user/list_form.html', {'forms': forms})

@login_required
def list_submitted_forms_views(request):
    # Người dùng thường chỉ xem đơn của chính mình, Admin/Checker/Manager được xem tất cả
    is_checker = request.user.groups.filter(name='Checker').exists()
    is_manager = request.user.groups.filter(name='Manager').exists()
    
    if request.user.is_superuser or is_checker or is_manager:
        submissions = FormSubmission.objects.select_related('form_definition', 'user').order_by('-submitted_at')
    else:
        submissions = FormSubmission.objects.filter(user=request.user).select_related('form_definition').order_by('-submitted_at')
        
    context = {
        'submissions': submissions
    }
    return render(request, 'form_app/user/list_submit_form.html', context)

@login_required
def detail_submit_form_view(request, submission_id):
    submission = get_object_or_404(FormSubmission, id=submission_id)
    form_def = submission.form_definition
    
    # Phân quyền xem đơn
    is_checker = request.user.groups.filter(name='Checker').exists()
    is_manager = request.user.groups.filter(name='Manager').exists()
    is_owner = submission.user == request.user
    
    # Cho phép xem nếu là owner, checker, manager, admin HOẶC đơn đã được duyệt hoàn toàn (public nội bộ)
    if not (request.user.is_superuser or is_checker or is_manager or is_owner or submission.status == 'approved'):
        return HttpResponseForbidden("Bạn không có quyền xem chi tiết biểu mẫu này.")
        
    context = {
        'form_def': form_def,
        'submission': submission,
        'schema_json_str': json.dumps(form_def.schema_json),
        'submission_json_str': json.dumps(submission.data),
        'status': submission.status,
        'is_checker': is_checker or request.user.is_superuser,
        'is_manager': is_manager or request.user.is_superuser,
        'is_owner': is_owner,
    }
    return render(request, 'form_app/user/detail_submit_form.html', context)


class CancelSubmissionView(View):
    """API xử lý hủy đơn đã nộp (Chỉ người nộp đơn được hủy khi đơn đang ở trạng thái Chờ Checker duyệt)."""
    def post(self, request, submission_id):
        if not request.user.is_authenticated:
            return JsonResponse({'status': 'error', 'message': 'Yêu cầu đăng nhập.'}, status=401)
            
        submission = get_object_or_404(FormSubmission, id=submission_id)
        
        # Chỉ chủ đơn mới được hủy và đơn phải đang ở trạng thái pending_checker
        if submission.user != request.user and not request.user.is_superuser:
            return JsonResponse({'status': 'error', 'message': 'Bạn không phải là người tạo đơn này.'}, status=403)
            
        if submission.status == 'pending_checker':
            submission.status = 'cancelled'
            submission.save()
            return JsonResponse({'status': 'success', 'message': 'Hủy đơn thành công!'})
            
        return JsonResponse({'status': 'error', 'message': 'Đơn này đã được duyệt hoặc xử lý, không thể hủy.'}, status=400)


# ============================================================
# CLASS-BASED VIEWS FOR DRAFTS & FORM RENDERING
# ============================================================

class RenderFormView(View):
    """View hiển thị form điền thông tin và tự động load bản nháp nếu có tham số draft_id."""
    def get(self, request, form_id):
        form_def = get_object_or_404(FormDefinition, id=form_id, is_active=True)
        schema_json_str = json.dumps(form_def.schema_json)
        
        draft_id = request.GET.get('draft_id')
        draft_title = ""
        draft_data_json_str = "null"
        
        if draft_id:
            try:
                draft = FormDraft.objects.get(id=draft_id, form_definition=form_def)
                draft_title = draft.title
                draft_data_json_str = json.dumps(draft.data)
            except FormDraft.DoesNotExist:
                draft_id = None
                
        context = {
            'form_def': form_def,
            'schema_json_str': schema_json_str,
            'draft_id': draft_id,
            'draft_title': draft_title,
            'draft_data_json_str': draft_data_json_str,
        }
        return render(request, 'form_app/user/render_form.html', context)


class ListDraftsPageView(View):
    """View hiển thị trang danh sách các bản nháp đang dở."""
    def get(self, request):
        drafts = FormDraft.objects.select_related('form_definition').order_by('-updated_at')
        context = {
            'drafts': drafts
        }
        return render(request, 'form_app/user/list_draft.html', context)


class SubmitFormApiView(View):
    """API tiếp nhận dữ liệu nộp form chính thức và tự động xóa bản nháp tương ứng."""
    def post(self, request, form_id):
        form_def = get_object_or_404(FormDefinition, id=form_id, is_active=True)
        try:
            body = json.loads(request.body)
            submission_data = body.get('data', body) if isinstance(body, dict) and 'data' in body else body
            draft_id = body.get('draft_id') if isinstance(body, dict) else None

            # Lưu vào bảng FormSubmission với trạng thái chờ duyệt cấp 1 (pending_checker)
            submission = FormSubmission.objects.create(
                form_definition=form_def,
                data=submission_data,
                user=request.user if request.user.is_authenticated else None,
                status='pending_checker'
            )

            # Xóa bản nháp sau khi đã nộp chính thức thành công
            if draft_id:
                FormDraft.objects.filter(id=draft_id, form_definition=form_def).delete()
                
            # --- Bắn email thông báo cho Checker ---
            checker_emails = list(User.objects.filter(groups__name='Checker').exclude(email='').values_list('email', flat=True))
            if checker_emails:
                subject = f"[eForm] Có biểu mẫu mới cần kiểm duyệt: {form_def.title}"
                msg = f"Xin chào Checker,\n\nBiểu mẫu '{form_def.title}' vừa được nộp bởi {request.user.username if request.user.is_authenticated else 'Ẩn danh'} và đang chờ bạn kiểm duyệt.\nVui lòng truy cập hệ thống để xử lý.\n\nMã đơn: #{submission.id}\n\nTrân trọng,\nHệ thống eForm."
                send_email_async(subject, msg, checker_emails)

            return JsonResponse({'status': 'success', 'message': 'Nộp biểu mẫu thành công và đang chờ phê duyệt!'})

        except json.JSONDecodeError as e:
            return JsonResponse({'status': 'error', 'message': f'Dữ liệu JSON không hợp lệ: {str(e)}'}, status=400)
        except Exception as e:
            import traceback
            traceback.print_exc()
            return JsonResponse({'status': 'error', 'message': f'Lỗi server: {str(e)}'}, status=500)


class SaveDraftApiView(View):
    """API lưu hoặc cập nhật bản nháp từ form gửi lên."""
    def post(self, request, form_id):
        form_def = get_object_or_404(FormDefinition, id=form_id, is_active=True)
        try:
            body = json.loads(request.body)
            draft_data = body.get('data', {})
            draft_title = body.get('title', '')
            draft_id = body.get('draft_id')

            if draft_id:
                draft = get_object_or_404(FormDraft, id=draft_id, form_definition=form_def)
                draft.data = draft_data
                draft.title = draft_title
                draft.save()
            else:
                draft = FormDraft.objects.create(
                    form_definition=form_def,
                    data=draft_data,
                    title=draft_title,
                )

            return JsonResponse({
                'status': 'success',
                'message': 'Đã lưu nháp thành công!',
                'draft_id': draft.id,
                'updated_at': draft.updated_at.strftime('%d/%m/%Y %H:%M'),
            })
        except json.JSONDecodeError:
            return JsonResponse({'status': 'error', 'message': 'Dữ liệu JSON không hợp lệ.'}, status=400)
        except Exception as e:
            import traceback
            traceback.print_exc()
            return JsonResponse({'status': 'error', 'message': f'Lỗi server: {str(e)}'}, status=500)


class ListDraftsApiView(View):
    """API lấy dữ liệu danh sách bản nháp của một form cụ thể dưới dạng JSON."""
    def get(self, request, form_id):
        form_def = get_object_or_404(FormDefinition, id=form_id, is_active=True)
        drafts = FormDraft.objects.filter(form_definition=form_def)
        result = [{
            'id': d.id,
            'title': d.title or 'Nháp chưa đặt tên',
            'updated_at': d.updated_at.strftime('%d/%m/%Y %H:%M'),
            'created_at': d.created_at.strftime('%d/%m/%Y %H:%M'),
        } for d in drafts]
        return JsonResponse({'status': 'success', 'drafts': result})


class LoadDraftApiView(View):
    """API tải thông tin chi tiết một bản nháp cụ thể dưới dạng JSON."""
    def get(self, request, form_id, draft_id):
        form_def = get_object_or_404(FormDefinition, id=form_id, is_active=True)
        draft = get_object_or_404(FormDraft, id=draft_id, form_definition=form_def)
        return JsonResponse({
            'status': 'success',
            'draft': {
                'id': draft.id,
                'title': draft.title,
                'data': draft.data,
                'updated_at': draft.updated_at.strftime('%d/%m/%Y %H:%M'),
            }
        })


class DeleteDraftApiView(View):
    """API xóa một bản nháp."""
    def delete(self, request, form_id, draft_id):
        form_def = get_object_or_404(FormDefinition, id=form_id, is_active=True)
        draft = get_object_or_404(FormDraft, id=draft_id, form_definition=form_def)
        draft.delete()
        return JsonResponse({'status': 'success', 'message': 'Đã xóa bản nháp.'})


# ============================================================
# PUBLIC APPROVED FORMS VIEW
# ============================================================

class PublicApprovedFormsView(View):
    """View hiển thị danh sách các biểu mẫu đã được phê duyệt thành công cho tất cả người dùng."""
    @method_decorator(login_required)
    def get(self, request):
        # Lấy tất cả các đơn có status = 'approved', 'pending_cancel_checker', 'pending_cancel_manager', 'revoked'
        submissions = FormSubmission.objects.filter(
            status__in=['approved', 'pending_cancel_checker', 'pending_cancel_manager', 'revoked']
        ).select_related('form_definition', 'user').order_by('-approved_at')
        
        context = {
            'submissions': submissions
        }
        return render(request, 'form_app/user/public_approved_list.html', context)


# ============================================================
# RBAC APPROVAL SYSTEM VIEWS
# ============================================================

class ApproveListView(View):
    """View hiển thị danh sách các đơn cần phê duyệt hoặc cần hủy tùy theo quyền hạn của người đăng nhập."""
    @method_decorator(login_required)
    def get(self, request):
        is_checker = request.user.groups.filter(name='Checker').exists()
        is_manager = request.user.groups.filter(name='Manager').exists()
        
        submissions = []
        
        # Nếu là Superuser: Xem toàn bộ các đơn đang chờ duyệt và xin hủy
        if request.user.is_superuser:
            submissions = FormSubmission.objects.filter(
                status__in=['pending_checker', 'pending_manager', 'pending_cancel_checker', 'pending_cancel_manager']
            ).select_related('form_definition', 'user').order_by('-submitted_at')
        else:
            if is_manager:
                submissions = FormSubmission.objects.filter(
                    status__in=['pending_manager', 'pending_cancel_manager']
                ).select_related('form_definition', 'user').order_by('-submitted_at')
            elif is_checker:
                submissions = FormSubmission.objects.filter(
                    status__in=['pending_checker', 'pending_cancel_checker']
                ).select_related('form_definition', 'user').order_by('-submitted_at')
                
        context = {
            'submissions': submissions,
            'is_checker': is_checker,
            'is_manager': is_manager,
        }
        return render(request, 'form_app/user/approve_list.html', context)


class ApproveSubmissionView(View):
    """API tiếp nhận quyết định duyệt (Approve/Reject) từ Checker và Manager."""
    @method_decorator(login_required)
    def post(self, request, submission_id):
        submission = get_object_or_404(FormSubmission, id=submission_id)
        is_checker = request.user.groups.filter(name='Checker').exists()
        is_manager = request.user.groups.filter(name='Manager').exists()
        
        try:
            body = json.loads(request.body)
            action = body.get('action')  # 'approve' hoặc 'reject'
            comment = body.get('comment', '').trim() if body.get('comment') else ''
        except json.JSONDecodeError:
            return JsonResponse({'status': 'error', 'message': 'Dữ liệu gửi lên không đúng định dạng.'}, status=400)
            
        if not action in ['approve', 'reject']:
            return JsonResponse({'status': 'error', 'message': 'Hành động không hợp lệ.'}, status=400)

        # 1. Xử lý cấp duyệt của Checker (Cấp 1)
        if submission.status == 'pending_checker':
            if not (is_checker or request.user.is_superuser):
                return JsonResponse({'status': 'error', 'message': 'Bạn không có quyền duyệt cấp này (Checker).'}, status=403)
                
            if action == 'approve':
                submission.status = 'pending_manager' # Chuyển lên cho Manager duyệt
                # Bắn email cho Manager
                manager_emails = list(User.objects.filter(groups__name='Manager').exclude(email='').values_list('email', flat=True))
                if manager_emails:
                    subject = f"[eForm] Đơn #{submission.id} cần Manager phê duyệt"
                    msg = f"Xin chào Manager,\n\nBiểu mẫu '{submission.form_definition.title}' (Mã đơn: #{submission.id}) đã được Checker ({request.user.username}) đồng ý và đang chờ bạn phê duyệt cuối cùng.\n\nÝ kiến Checker: {comment}\n\nVui lòng đăng nhập hệ thống để xử lý.\n\nTrân trọng,\nHệ thống eForm."
                    send_email_async(subject, msg, manager_emails)
            else:
                submission.status = 'rejected'
                # Bắn email báo từ chối cho người nộp
                if submission.user and submission.user.email:
                    subject = f"[eForm] Biểu mẫu #{submission.id} đã bị từ chối"
                    msg = f"Xin chào {submission.user.username},\n\nRất tiếc, biểu mẫu '{submission.form_definition.title}' của bạn đã bị từ chối bởi Checker ({request.user.username}).\n\nLý do/Ý kiến: {comment}\n\nTrân trọng,\nHệ thống eForm."
                    send_email_async(subject, msg, [submission.user.email])
                
            submission.checked_by = request.user
            submission.checked_at = timezone.now()
            submission.checker_comment = comment
            submission.save()
            return JsonResponse({'status': 'success', 'message': 'Đã cập nhật quyết định duyệt của Checker.'})
            
        # 2. Xử lý cấp duyệt của Manager (Cấp 2)
        elif submission.status == 'pending_manager':
            if not (is_manager or request.user.is_superuser):
                return JsonResponse({'status': 'error', 'message': 'Bạn không có quyền phê duyệt cấp này (Manager).'}, status=403)
                
            if action == 'approve':
                submission.status = 'approved' # Đã duyệt hoàn toàn
                # Bắn email báo thành công cho người nộp
                if submission.user and submission.user.email:
                    subject = f"[eForm] Xin chúc mừng, biểu mẫu #{submission.id} đã được phê duyệt"
                    msg = f"Xin chào {submission.user.username},\n\nBiểu mẫu '{submission.form_definition.title}' của bạn đã được phê duyệt hoàn tất bởi Manager ({request.user.username}).\n\nÝ kiến Manager: {comment}\n\nTrân trọng,\nHệ thống eForm."
                    send_email_async(subject, msg, [submission.user.email])
            else:
                submission.status = 'rejected'
                # Bắn email báo từ chối cho người nộp
                if submission.user and submission.user.email:
                    subject = f"[eForm] Biểu mẫu #{submission.id} đã bị từ chối"
                    msg = f"Xin chào {submission.user.username},\n\nRất tiếc, biểu mẫu '{submission.form_definition.title}' của bạn đã bị từ chối bởi Manager ({request.user.username}).\n\nLý do/Ý kiến: {comment}\n\nTrân trọng,\nHệ thống eForm."
                    send_email_async(subject, msg, [submission.user.email])
                
            submission.approved_by = request.user
            submission.approved_at = timezone.now()
            submission.manager_comment = comment
            submission.save()
            return JsonResponse({'status': 'success', 'message': 'Đã cập nhật quyết định phê duyệt của Manager.'})
            
        # 3. Xử lý cấp duyệt HỦY của Checker (Cấp 1)
        elif submission.status == 'pending_cancel_checker':
            if not (is_checker or request.user.is_superuser):
                return JsonResponse({'status': 'error', 'message': 'Bạn không có quyền duyệt cấp này.'}, status=403)
                
            if action == 'approve':
                submission.status = 'pending_cancel_manager' # Chuyển lên Manager duyệt hủy
            else:
                submission.status = 'approved' # Từ chối hủy thì quay về trạng thái đã duyệt
                
            submission.checked_by = request.user
            submission.checked_at = timezone.now()
            submission.checker_comment = f"Về việc xin hủy: {comment}"
            submission.save()
            return JsonResponse({'status': 'success', 'message': 'Đã xử lý yêu cầu xin hủy của Checker.'})
            
        # 4. Xử lý cấp duyệt HỦY của Manager (Cấp 2)
        elif submission.status == 'pending_cancel_manager':
            if not (is_manager or request.user.is_superuser):
                return JsonResponse({'status': 'error', 'message': 'Bạn không có quyền duyệt cấp này.'}, status=403)
                
            if action == 'approve':
                submission.status = 'revoked' # Hủy thành công
            else:
                submission.status = 'approved' # Từ chối hủy thì quay về đã duyệt
                
            submission.approved_by = request.user
            submission.approved_at = timezone.now()
            submission.manager_comment = f"Về việc xin hủy: {comment}"
            submission.save()
            return JsonResponse({'status': 'success', 'message': 'Đã xử lý yêu cầu xin hủy của Manager.'})
            
        return JsonResponse({'status': 'error', 'message': 'Đơn này đang không ở trạng thái chờ duyệt.'}, status=400)


class RequestRevokeApiView(View):
    """API cho phép chủ đơn xin hủy biểu mẫu đã được duyệt."""
    @method_decorator(login_required)
    def post(self, request, submission_id):
        submission = get_object_or_404(FormSubmission, id=submission_id)
        if submission.user != request.user and not request.user.is_superuser:
            return JsonResponse({'status': 'error', 'message': 'Chỉ người nộp mới được xin hủy đơn này.'}, status=403)
            
        if submission.status != 'approved':
            return JsonResponse({'status': 'error', 'message': 'Chỉ có thể xin hủy những đơn đã được duyệt hoàn toàn.'}, status=400)
            
        submission.status = 'pending_cancel_checker'
        # Reset ý kiến cũ để dành cho việc duyệt hủy
        submission.checker_comment = ''
        submission.manager_comment = ''
        submission.checked_by = None
        submission.approved_by = None
        submission.save()
        return JsonResponse({'status': 'success', 'message': 'Đã gửi yêu cầu xin hủy biểu mẫu tới Checker.'})


@staff_member_required
def admin_form_design_view(request, form_id):
    form_def = get_object_or_404(FormDefinition, id=form_id)
    
    if request.method == 'POST':
        try:
            payload = json.loads(request.body)
            form_def.schema_json = payload.get('schema', {})
            form_def.save()
            return JsonResponse({'status': 'success', 'message': 'Đã lưu cấu trúc form thành công!'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
        
    context = {
        'form_def': form_def,
        'schema_json_str': json.dumps(form_def.schema_json)
    }
    return render(request, 'form_app/admin/builder_form.html', context)


def upload_file_to_minio(request):
    """
    Nhận file từ Form.io custom storage provider 'django',
    đẩy lên MinIO và trả về URL có thể truy cập được.
    CSRF được xác thực qua header X-CSRFToken (gửi từ frontend).
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Chỉ chấp nhận phương thức POST.'}, status=405)

    uploaded_file = request.FILES.get('file')
    if not uploaded_file:
        return JsonResponse({'error': 'Không tìm thấy file trong request.'}, status=400)

    try:
        client = get_minio_client()
        bucket = settings.MINIO_BUCKET_NAME

        # Tạo tên file duy nhất để tránh ghi đè
        ext = os.path.splitext(uploaded_file.name)[1]
        unique_name = f"uploads/{uuid.uuid4().hex}{ext}"

        # Upload lên MinIO
        client.put_object(
            bucket_name=bucket,
            object_name=unique_name,
            data=uploaded_file,
            length=uploaded_file.size,
            content_type=uploaded_file.content_type,
        )

        # Tạo presigned URL cho phép truy cập file (hết hạn sau 7 ngày)
        file_url = client.presigned_get_object(
            bucket_name=bucket,
            object_name=unique_name,
            expires=timedelta(days=7),
        )

        return JsonResponse({
            'storage': 'django',
            'name': uploaded_file.name,
            'originalName': uploaded_file.name,
            'size': uploaded_file.size,
            'type': uploaded_file.content_type,
            'url': file_url,
        }, status=200)

    except Exception as e:
        return JsonResponse({'error': f'Lỗi upload lên MinIO: {str(e)}'}, status=500)