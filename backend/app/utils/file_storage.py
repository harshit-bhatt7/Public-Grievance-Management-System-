"""
Attachment file storage.

Actual file bytes are stored on disk (never in PostgreSQL), under:

    <UPLOAD_DIR>/grievances/<grievance_number>/<generated-uuid>.<ext>

Security measures implemented here:
- The on-disk filename is always a freshly generated UUID + a validated
  extension — the client-supplied filename is NEVER used as a path
  component, which eliminates path traversal by construction (there is
  no user-controlled string in the filesystem path at all, aside from
  the server-generated `grievance_number`, which is validated separately).
- Extension is checked against an allow-list.
- MIME type (as reported by the client) is checked against an allow-list.
  This is a basic check, not a substitute for real content sniffing / AV
  scanning — see the "Future File Security" note in docs/architecture.md
  for what Step 12 should add.
- Size is enforced while streaming to disk (reads in chunks and aborts
  once the configured limit is exceeded), rather than trusting a
  Content-Length header.
- The SHA-256 hash is always computed server-side from the bytes actually
  written to disk — a client-supplied hash is never accepted or trusted.
"""
import hashlib
import re
import uuid
from pathlib import Path
from typing import BinaryIO

from fastapi import HTTPException, UploadFile, status

from app.core.config import get_settings

settings = get_settings()

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf"}
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "application/pdf"}

GRIEVANCE_NUMBER_PATTERN = re.compile(r"^[A-Z0-9\-]{1,30}$")

_CHUNK_SIZE = 1024 * 1024  # 1 MB


def get_upload_root() -> Path:
    """
    Resolve UPLOAD_DIR relative to the backend project root (the directory
    containing `app/`), regardless of the process's current working directory.
    """
    upload_dir = Path(settings.UPLOAD_DIR)
    if upload_dir.is_absolute():
        return upload_dir
    backend_root = Path(__file__).resolve().parents[2]  # app/utils/ -> app/ -> backend/
    return backend_root / upload_dir


def _validate_grievance_number(grievance_number: str) -> None:
    """Defense in depth: even though we generate grievance numbers ourselves,
    validate the format before ever using one as a directory name."""
    if not GRIEVANCE_NUMBER_PATTERN.match(grievance_number):
        raise ValueError(f"Unexpected grievance number format: {grievance_number!r}")


def validate_extension(filename: str) -> str:
    extension = Path(filename or "").suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type. Allowed extensions: {', '.join(sorted(ALLOWED_EXTENSIONS))}.",
        )
    return extension


def validate_mime_type(content_type: str | None) -> str:
    if content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file type. Only JPG, PNG, and PDF files are allowed.",
        )
    return content_type


def sanitize_display_filename(filename: str) -> str:
    """
    Produce a safe filename for *display/storage-as-metadata* purposes only
    (never used to build a filesystem path). Strips any directory
    components and disallowed characters.
    """
    base_name = Path(filename or "upload").name  # drops any directory components, incl. ../
    base_name = re.sub(r"[^A-Za-z0-9._\-]", "_", base_name)
    return base_name[:255] or "upload"


def _validate_file_signature(path: Path, extension: str) -> None:
    """Basic content-signature validation to reject obvious MIME/extension spoofing."""
    with open(path, "rb") as fh:
        header = fh.read(8)
    valid = {
        ".pdf": header.startswith(b"%PDF-"),
        ".png": header.startswith(b"\x89PNG\r\n\x1a\n"),
        ".jpg": header.startswith(b"\xff\xd8\xff"),
        ".jpeg": header.startswith(b"\xff\xd8\xff"),
    }
    if not valid.get(extension, False):
        path.unlink(missing_ok=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File content does not match the allowed file type.")


def save_attachment_file(grievance_number: str, upload_file: UploadFile) -> dict:
    """
    Stream an uploaded file to disk with size enforcement, returning
    metadata to persist on the Attachment row. Raises HTTPException for
    any validation failure.
    """
    _validate_grievance_number(grievance_number)

    extension = validate_extension(upload_file.filename or "")
    validate_mime_type(upload_file.content_type)

    display_name = sanitize_display_filename(upload_file.filename or "upload")
    stored_name = f"{uuid.uuid4().hex}{extension}"

    grievance_dir = get_upload_root() / "grievances" / grievance_number
    grievance_dir.mkdir(parents=True, exist_ok=True)

    destination = grievance_dir / stored_name
    # Belt-and-suspenders: confirm the resolved path is still inside the
    # intended grievance directory before writing anything.
    if grievance_dir.resolve() not in destination.resolve().parents:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid file destination.")

    max_bytes = settings.max_attachment_size_bytes
    sha256 = hashlib.sha256()
    total_bytes = 0

    try:
        with open(destination, "wb") as out_file:
            while True:
                chunk = upload_file.file.read(_CHUNK_SIZE)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > max_bytes:
                    out_file.close()
                    destination.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"File exceeds the {settings.MAX_ATTACHMENT_SIZE_MB} MB size limit.",
                    )
                sha256.update(chunk)
                out_file.write(chunk)
    except HTTPException:
        raise
    except OSError as exc:
        destination.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not store the uploaded file.",
        ) from exc

    if total_bytes == 0:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty.")
    _validate_file_signature(destination, extension)

    relative_path = str(Path("grievances") / grievance_number / stored_name)

    return {
        "file_name": display_name,
        "file_type": upload_file.content_type,
        "file_size": total_bytes,
        "file_path": relative_path,
        "file_hash": sha256.hexdigest(),
    }


def save_resolution_evidence_file(grievance_number: str, resolution_id: str, upload_file: UploadFile) -> dict:
    """Store officer resolution evidence using the same security controls as Step 3.

    Files are stored under a server-generated UUID path and only metadata is
    persisted in PostgreSQL. The resolution/grievance identifiers are validated
    before becoming path components.
    """
    _validate_grievance_number(grievance_number)
    if not re.fullmatch(r"[0-9a-fA-F\-]{36}", resolution_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid resolution identifier.")

    extension = validate_extension(upload_file.filename or "")
    validate_mime_type(upload_file.content_type)
    display_name = sanitize_display_filename(upload_file.filename or "upload")
    stored_name = f"{uuid.uuid4().hex}{extension}"

    resolution_dir = get_upload_root() / "grievances" / grievance_number / "resolutions" / resolution_id
    resolution_dir.mkdir(parents=True, exist_ok=True)
    destination = resolution_dir / stored_name
    if resolution_dir.resolve() not in destination.resolve().parents:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid file destination.")

    max_bytes = settings.max_attachment_size_bytes
    sha256 = hashlib.sha256()
    total_bytes = 0
    try:
        with open(destination, "wb") as out_file:
            while True:
                chunk = upload_file.file.read(_CHUNK_SIZE)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > max_bytes:
                    out_file.close()
                    destination.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"File exceeds the {settings.MAX_ATTACHMENT_SIZE_MB} MB size limit.",
                    )
                sha256.update(chunk)
                out_file.write(chunk)
    except HTTPException:
        raise
    except OSError as exc:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not store the uploaded file.") from exc

    if total_bytes == 0:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty.")

    return {
        "file_name": display_name,
        "file_type": upload_file.content_type,
        "file_size": total_bytes,
        "file_path": str(Path("grievances") / grievance_number / "resolutions" / resolution_id / stored_name),
        "file_hash": sha256.hexdigest(),
    }


def remove_stored_file(relative_path: str) -> None:
    """Best-effort cleanup for a file whose DB transaction was rolled back."""
    try:
        root = get_upload_root().resolve()
        target = (root / relative_path).resolve()
        if root not in target.parents:
            return
        target.unlink(missing_ok=True)
    except OSError:
        # Cleanup failure must not hide the original transaction error.
        pass


def save_project_file(project_id: str, upload_file: UploadFile, images_only: bool = False) -> dict:
    """Store public-project evidence using the same UUID, signature, size and path controls."""
    if not re.fullmatch(r"[0-9a-fA-F\-]{36}", project_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid project identifier.")
    extension = validate_extension(upload_file.filename or "")
    mime = validate_mime_type(upload_file.content_type)
    if images_only and mime not in {"image/jpeg", "image/png"}:
        raise HTTPException(status_code=400, detail="Project photographs must be JPG or PNG files.")
    display_name = sanitize_display_filename(upload_file.filename or "upload")
    stored_name = f"{uuid.uuid4().hex}{extension}"
    project_dir = get_upload_root() / "projects" / project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    destination = project_dir / stored_name
    if project_dir.resolve() not in destination.resolve().parents:
        raise HTTPException(status_code=400, detail="Invalid file destination.")
    max_bytes=settings.max_attachment_size_bytes; sha256=hashlib.sha256(); total=0
    try:
        with open(destination,"wb") as out:
            while True:
                chunk=upload_file.file.read(_CHUNK_SIZE)
                if not chunk: break
                total += len(chunk)
                if total>max_bytes:
                    out.close(); destination.unlink(missing_ok=True)
                    raise HTTPException(status_code=413, detail=f"File exceeds the {settings.MAX_ATTACHMENT_SIZE_MB} MB size limit.")
                sha256.update(chunk); out.write(chunk)
    except HTTPException: raise
    except OSError as exc:
        destination.unlink(missing_ok=True); raise HTTPException(status_code=500,detail="Could not store the uploaded file.") from exc
    if total==0:
        destination.unlink(missing_ok=True); raise HTTPException(status_code=400,detail="Uploaded file is empty.")
    _validate_file_signature(destination, extension)
    return {"file_name":display_name,"file_type":mime,"file_size":total,"file_path":str(Path("projects")/project_id/stored_name),"file_hash":sha256.hexdigest()}
