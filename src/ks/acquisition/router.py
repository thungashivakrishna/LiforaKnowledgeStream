"""Acquisition router — API endpoints for fetching document content."""
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database import get_db_session
from ks.acquisition.schemas import FetchRequest, FetchRunResponse
from ks.acquisition.service import AcquisitionService

router = APIRouter(prefix="/acquisition", tags=["Acquisition"])


@router.post("/fetch", response_model=FetchRunResponse)
async def start_fetch(
    data: FetchRequest, 
    db: AsyncSession = Depends(get_db_session)
):
    """Start an acquisition fetch run for a specific document."""
    service = AcquisitionService(db)
    try:
        run = await service.start_fetch(data)
        await db.commit()
        return run
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/runs", response_model=dict)
async def list_fetch_runs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db_session)
):
    """List acquisition fetch runs with pagination."""
    service = AcquisitionService(db)
    items, total = await service.list_fetch_runs(limit, offset)
    
    # Format for response
    formatted_items = [
        {
            "id": r.id,
            "document_id": r.document_id,
            "status": r.status,
            "started_at": r.started_at,
            "completed_at": r.completed_at,
            "error_message": r.error_message,
        } for r in items
    ]
    
    return {"items": formatted_items, "total": total, "limit": limit, "offset": offset}


@router.get("/runs/{run_id}", response_model=FetchRunResponse)
async def get_fetch_run(run_id: uuid.UUID, db: AsyncSession = Depends(get_db_session)):
    """Get details of a specific fetch run."""
    service = AcquisitionService(db)
    try:
        run = await service.get_fetch_run(run_id)
        return run
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

from fastapi import UploadFile, File, Form
import hashlib
from ks.domain.models import DocumentRegistry, DocumentVersion
from ks.domain.enums import DocumentStatus

@router.post("/upload")
async def upload_diagnostic_report(
    file: UploadFile = File(...),
    source_id: uuid.UUID = Form(...),
    db: AsyncSession = Depends(get_db_session)
):
    """Directly upload a diagnostic PDF or Image for vision processing."""
    content = await file.read()
    
    # Simple hash
    hasher = hashlib.sha256()
    hasher.update(content)
    content_hash = hasher.hexdigest()
    
    # Get Minio client
    from ks.config.settings import get_settings
    from minio import Minio
    import io
    settings = get_settings()
    minio_client = Minio(
        settings.minio.endpoint,
        access_key=settings.minio.access_key,
        secret_key=settings.minio.secret_key,
        secure=settings.minio.secure
    )
    
    # Create document entry
    doc_id = uuid.uuid4()
    doc = DocumentRegistry(
        id=doc_id,
        source_id=source_id,
        title=file.filename,
        canonical_url=f"upload://{file.filename}",
        status=DocumentStatus.FETCHED,
        content_hash=content_hash
    )
    db.add(doc)
    
    # Store in minio
    ext = file.filename.split(".")[-1] if "." in file.filename else "bin"
    object_key = f"{doc_id}/{content_hash}.{ext}"
    
    if not minio_client.bucket_exists(settings.minio.bucket_raw):
        minio_client.make_bucket(settings.minio.bucket_raw)
        
    minio_client.put_object(
        settings.minio.bucket_raw,
        object_key,
        io.BytesIO(content),
        length=len(content),
        content_type=file.content_type or "application/octet-stream"
    )
    
    doc.raw_object_key = object_key
    
    version = DocumentVersion(
        id=uuid.uuid4(),
        document_id=doc_id,
        version_hash=content_hash,
        raw_object_key=object_key
    )
    db.add(version)
    await db.commit()
    
    # Trigger Extraction Workflow
    from temporalio.client import Client
    client = await Client.connect(f"{settings.temporal.host}:{settings.temporal.port}")
    run_id = uuid.uuid4()
    
    # Create extraction run record
    from ks.domain.models import ExtractionRun
    from ks.domain.enums import RunStatus
    ext_run = ExtractionRun(id=run_id, document_id=doc_id, status=RunStatus.PENDING)
    db.add(ext_run)
    await db.commit()
    
    await client.execute_workflow(
        "ExtractionWorkflow",
        {
            "run_id": str(run_id),
            "document_id": str(doc_id),
            "raw_object_key": object_key,
            "use_ocr": True, # Force OCR for uploads
            "use_llm": True  # Force Layout parsing
        },
        id=f"extraction-{run_id}",
        task_queue=settings.temporal.task_queue,
    )
    
    return {"message": "Diagnostic report uploaded and processing started.", "document_id": str(doc_id)}
