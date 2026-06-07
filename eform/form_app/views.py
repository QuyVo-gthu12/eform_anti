from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render, get_object_or_404
from .models import FormDefinition, FormSubmission
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

def render_form_view(request, form_id):
    form_def = get_object_or_404(FormDefinition, id=form_id, is_active=True)
    schema_json_str =json.dumps(form_def.schema_json)
    context = {
        'form_def': form_def,
        'schema_json_str': schema_json_str
    }
    return render(request, 'form_app/user/render_form.html', context)

def submit_form_api(request, form_id):
    if request.method == 'POST':
        form_def = get_object_or_404(FormDefinition, id=form_id, is_active=True)
        try:
            # Đọc payload JSON dữ liệu mà Form.io gửi lên
            submission_data = json.loads(request.body)

            # Lưu toàn bộ dữ liệu ô nhập vào bảng FormSubmission
            FormSubmission.objects.create(
                form_definition=form_def,
                data=submission_data
            )

            return JsonResponse({'status': 'success', 'message': 'Nộp biểu mẫu thành công!'})

        except json.JSONDecodeError as e:
            return JsonResponse({'status': 'error', 'message': f'Dữ liệu JSON không hợp lệ: {str(e)}'}, status=400)

        except Exception as e:
            import traceback
            traceback.print_exc()  # In traceback đầy đủ ra Django server console để debug
            return JsonResponse({'status': 'error', 'message': f'Lỗi server: {str(e)}'}, status=500)

    return JsonResponse({'status': 'error', 'message': 'Phương thức không được phép.'}, status=405)

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