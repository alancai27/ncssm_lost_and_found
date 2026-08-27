"""
Where uploaded photos live.

Locally that is the filesystem, which is simple and needs no accounts. In
production it cannot be: Render's free instances get a fresh, empty disk on
every deploy and every restart, so anything written at runtime disappears.
Set the S3_* variables and photos go to object storage instead -- any
S3-compatible service works (Cloudflare R2, Backblaze B2, Supabase Storage,
MinIO, S3 itself).

Photos are streamed back through the app rather than linked directly, so the
bucket can stay private and there is nothing extra to configure.
"""

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads")

S3_BUCKET = os.environ.get("S3_BUCKET", "").strip()
S3_ENDPOINT = os.environ.get("S3_ENDPOINT_URL", "").strip()
S3_KEY_ID = os.environ.get("S3_ACCESS_KEY_ID", "").strip()
S3_SECRET = os.environ.get("S3_SECRET_ACCESS_KEY", "").strip()
S3_REGION = os.environ.get("S3_REGION", "auto").strip()
S3_PREFIX = os.environ.get("S3_PREFIX", "uploads/").strip()

_client = None


def using_s3():
    return bool(S3_BUCKET and S3_KEY_ID and S3_SECRET)


def backend_name():
    if not using_s3():
        return "local filesystem (static/uploads)"
    where = S3_ENDPOINT or "AWS S3"
    return f"object storage ({S3_BUCKET} at {where})"


def _s3():
    global _client
    if _client is None:
        import boto3
        from botocore.config import Config

        _client = boto3.client(
            "s3",
            endpoint_url=S3_ENDPOINT or None,
            aws_access_key_id=S3_KEY_ID,
            aws_secret_access_key=S3_SECRET,
            region_name=S3_REGION,
            # R2 and most non-AWS endpoints want path-style addressing.
            config=Config(s3={"addressing_style": "path"}, signature_version="s3v4"),
        )
    return _client


def _key(name):
    return f"{S3_PREFIX}{name}"


def save(name, data, content_type="image/jpeg"):
    if using_s3():
        _s3().put_object(
            Bucket=S3_BUCKET, Key=_key(name), Body=data,
            ContentType=content_type, CacheControl="public, max-age=31536000",
        )
    else:
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        with open(os.path.join(UPLOAD_DIR, name), "wb") as fh:
            fh.write(data)


def load(name):
    """Return (bytes, content_type), or (None, None) if it isn't there."""
    if using_s3():
        try:
            obj = _s3().get_object(Bucket=S3_BUCKET, Key=_key(name))
        except Exception:
            return None, None
        return obj["Body"].read(), obj.get("ContentType", "image/jpeg")

    path = os.path.join(UPLOAD_DIR, name)
    if not os.path.exists(path):
        return None, None
    with open(path, "rb") as fh:
        return fh.read(), "image/jpeg"


def delete(name):
    if using_s3():
        try:
            _s3().delete_object(Bucket=S3_BUCKET, Key=_key(name))
        except Exception:
            pass
    else:
        path = os.path.join(UPLOAD_DIR, name)
        if os.path.exists(path):
            os.remove(path)


def check():
    """Round-trip a small object so misconfiguration surfaces at boot, not on
    a student's first upload."""
    probe = "_healthcheck.txt"
    payload = b"ok"
    save(probe, payload, "text/plain")
    got, _ = load(probe)
    delete(probe)
    if got != payload:
        raise RuntimeError(f"Storage round-trip failed for {backend_name()}")
    return True
