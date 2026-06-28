from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render, get_object_or_404
from django.utils.decorators import method_decorator
from django.views import View
from .models import FormDefinition, FormSubmission, FormDraft
import json
import uuid
import os
from django.conf import settings
from django.http import JsonResponse
from .minio_client import get_minio_client
from datetime import timedelta

def home_view(request):
    return render(request, "form_app/user/home.html")

def list_forms_view(request):
    # Lấy các form đang active từ database
    forms = FormDefinition.objects.filter(is_active=True).order_by('-created_at')
    return render(request, 'form_app/user/list_form.html', {'forms': forms})

def list_submitted_forms_views(request):
    submissions = FormSubmission.objects.select_related('form_definition').order_by('-submitted_at')
    context = {
        'submissions': submissions
    }
    return render(request, 'form_app/user/list_submit_form.html', context)

def detail_submit_form_view(request, submission_id):
    # 1. Tìm bản ghi kết quả nộp dựa trên ID
    submission = get_object_or_404(FormSubmission, id=submission_id)
    # 2. Lấy cấu trúc form gốc tương ứng
    form_def = submission.form_definition
    context = {
        'form_def': form_def,
        'submission': submission,
        # Chuyển cấu trúc form và dữ liệu nhập thành chuỗi JSON an toàn cho JS
        'schema_json_str': json.dumps(form_def.schema_json),
        'submission_json_str': json.dumps(submission.data),
        'status': submission.status,
    }
    return render(request, 'form_app/user/detail_submit_form.html', context)


class CancelSubmissionView(View):
    """API xử lý hủy đơn đã nộp."""
    def post(self, request, submission_id):
        submission = get_object_or_404(FormSubmission, id=submission_id)
        if submission.status == 'submitted':
            submission.status = 'cancelled'
            submission.save()
            return JsonResponse({'status': 'success', 'message': 'Hủy đơn thành công!'})
        return JsonResponse({'status': 'error', 'message': 'Đơn này không thể hủy hoặc đã được xử lý.'}, status=400)



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

            # Lưu vào bảng FormSubmission
            FormSubmission.objects.create(
                form_definition=form_def,
                data=submission_data
            )

            # Xóa bản nháp sau khi đã nộp chính thức thành công
            if draft_id:
                FormDraft.objects.filter(id=draft_id, form_definition=form_def).delete()

            return JsonResponse({'status': 'success', 'message': 'Nộp biểu mẫu thành công!'})

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