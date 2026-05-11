"""Extraction activities — worker tasks for extracting text from raw artifacts."""
import io
import logging
import uuid
from datetime import datetime

import httpx
from bs4 import BeautifulSoup
from minio import Minio
from temporalio import activity
from PIL import Image
import pytesseract
import litellm
import pdfminer.high_level

from ks.config.settings import get_settings
from ks.domain.enums import RunStatus, ExtractionQuality
from ks.domain.models import ExtractionRun


logger = logging.getLogger(__name__)


class ExtractionActivities:
    def __init__(self, minio_client: Minio):
        self.minio_client = minio_client
        self.settings = get_settings()

    @activity.defn
    async def fetch_raw_artifact(self, payload: dict) -> dict:
        """
        Fetches the raw artifact from MinIO.
        Payload keys: raw_object_key
        """
        object_key = payload["raw_object_key"]
        bucket = self.settings.minio.bucket_raw
        
        logger.info(f"Fetching raw artifact from MinIO: {bucket}/{object_key}")
        
        try:
            response = self.minio_client.get_object(bucket, object_key)
            content = response.read()
            response.close()
            response.release_conn()
            
            return {
                "object_key": object_key,
                "content": content,
                "success": True
            }
        except Exception as e:
            logger.error(f"Failed to fetch artifact {object_key}: {e}")
            return {"success": False, "error": str(e)}

    @activity.defn
    async def extract_text(self, payload: dict) -> dict:
        """
        Extracts text from raw content (HTML/PDF/Image) using standard libs, OCR, or LLM.
        Payload keys: object_key, content (bytes), use_ocr (bool), use_llm (bool)
        """
        object_key = payload["object_key"]
        content = payload["content"]
        
        # Temporal JSON converter might turn bytes into a list of ints
        if isinstance(content, list):
            content = bytes(content)
        use_ocr = payload.get("use_ocr", False)
        use_llm = payload.get("use_llm", False)
        
        ext = object_key.split(".")[-1].lower() if "." in object_key else ""
        extracted_text = ""
        quality = ExtractionQuality.HIGH
        
        try:
            if ext == "html" or ext == "htm":
                soup = BeautifulSoup(content, "lxml")
                # Remove scripts and styles
                for script in soup(["script", "style", "nav", "footer", "header"]):
                    script.extract()
                extracted_text = soup.get_text(separator="\n", strip=True)
                
            elif ext == "pdf":
                # First try pdfminer
                pdf_io = io.BytesIO(content)
                extracted_text = pdfminer.high_level.extract_text(pdf_io)
                
                # If text is very short, it might be a scanned PDF. Fallback to OCR if requested.
                if len(extracted_text.strip()) < 50 and use_ocr:
                    logger.info(f"PDF text extraction yielded little text. OCR not yet fully implemented for PDF pages in this prototype.")
                    quality = ExtractionQuality.LOW
                
            elif ext in ["png", "jpg", "jpeg"] and use_ocr:
                img = Image.open(io.BytesIO(content))
                extracted_text = pytesseract.image_to_string(img)
                quality = ExtractionQuality.MEDIUM
                
            else:
                extracted_text = content.decode("utf-8", errors="ignore")
                quality = ExtractionQuality.LOW

            # LLM Layout Parsing enhancement (if requested)
            if use_llm and extracted_text:
                logger.info("Enhancing extraction with LLM Layout Parsing...")
                # Note: litellm expects OPENAI_API_KEY or similar in environment.
                # This is a basic structural prompt.
                prompt = f"Please read the following raw text and restructure it into clean Markdown, preserving headers, lists, and paragraphs. Do not add any new information. \n\nRaw Text:\n{extracted_text[:4000]}" # Truncate for prototype to save context window
                try:
                    response = litellm.completion(
                        model="gpt-3.5-turbo", # Default fallback model, configure as needed
                        messages=[{"role": "user", "content": prompt}],
                    )
                    extracted_text = response.choices[0].message.content
                    quality = ExtractionQuality.HIGH
                except Exception as e:
                    logger.warning(f"LLM extraction failed, falling back to raw extracted text: {e}")
                    quality = ExtractionQuality.MEDIUM

            return {
                "success": True,
                "extracted_text": extracted_text,
                "quality": quality.value
            }
        except Exception as e:
            logger.error(f"Failed to extract text: {e}")
            return {"success": False, "error": str(e)}

    @activity.defn
    async def store_extracted_artifact(self, payload: dict) -> str:
        """
        Stores the extracted text in MinIO.
        Payload keys: object_key, extracted_text
        """
        orig_key = payload["object_key"]
        extracted_text = payload["extracted_text"]
        
        # New key: doc_id/hash.txt
        # Replace original extension with .txt
        if "." in orig_key:
            new_key = orig_key.rsplit(".", 1)[0] + ".txt"
        else:
            new_key = orig_key + ".txt"
            
        bucket = self.settings.minio.bucket_extracted
        logger.info(f"Storing extracted artifact in MinIO: {bucket}/{new_key}")
        
        if not self.minio_client.bucket_exists(bucket):
            self.minio_client.make_bucket(bucket)
            
        text_bytes = extracted_text.encode("utf-8")
        content_file = io.BytesIO(text_bytes)
        
        self.minio_client.put_object(
            bucket,
            new_key,
            content_file,
            length=len(text_bytes),
            content_type="text/plain"
        )
        
        return new_key

    @activity.defn
    async def update_extraction_status(self, payload: dict) -> None:
        """
        Updates the ExtractionRun status in the DB.
        """
        from apps.api.database import SessionLocal
        from sqlalchemy import select
        
        run_id = uuid.UUID(payload["run_id"])
        status = RunStatus(payload["status"])
        quality = ExtractionQuality(payload["quality"]) if payload.get("quality") else None
        error_msg = payload.get("error_message")
        
        from ks.domain.models import DocumentRegistry

        async with SessionLocal() as session:
            res = await session.execute(select(ExtractionRun).where(ExtractionRun.id == run_id))
            run = res.scalar_one_or_none()
            if run:
                run.status = status
                run.completed_at = datetime.now()
                run.error_message = error_msg
                run.extraction_quality = quality
                
                if status == RunStatus.COMPLETED and payload.get("extracted_object_key"):
                    doc_res = await session.execute(select(DocumentRegistry).where(DocumentRegistry.id == run.document_id))
                    doc = doc_res.scalar_one_or_none()
                    if doc:
                        doc.extracted_text_key = payload["extracted_object_key"]
            
            await session.commit()
