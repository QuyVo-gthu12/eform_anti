from minio import Minio
from django.conf import settings


def _build_client() -> Minio:
    # MINIO_SECURE phải là bool. settings.py đọc từ decouple nên cần ép kiểu ở đây.
    secure = str(settings.MINIO_SECURE).lower() in ('true', '1', 'yes')
    return Minio(
        endpoint=settings.MINIO_ENDPOINT,   # Phải là 'host:port', KHÔNG có http://
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=secure,
    )

def get_minio_client() -> Minio:
    client = _build_client()
    bucket = settings.MINIO_BUCKET_NAME
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)
    return client