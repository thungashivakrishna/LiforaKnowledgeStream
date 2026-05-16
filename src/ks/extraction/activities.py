"""Extraction activities — worker tasks for extracting text from raw artifacts."""
import io
import logging
import json
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
    async def perform_full_extraction(self, payload: dict) -> dict:
        """
        Unified Extraction Pipeline: Downloads raw content, extracts text, and uploads text in one step.
        Guarantees massive binary files never transit through Temporal gRPC workflow history.
        Payload keys: raw_object_key, use_ocr (bool), use_llm (bool)
        """
        raw_object_key = payload["raw_object_key"]
        use_ocr = payload.get("use_ocr", False)
        use_llm = payload.get("use_llm", False)
        
        raw_bucket = self.settings.minio.bucket_raw
        ext_bucket = self.settings.minio.bucket_extracted
        
        logger.info(f"Executing integrated extraction for: {raw_bucket}/{raw_object_key}")
        
        try:
            # 1. Fetch locally
            response = self.minio_client.get_object(raw_bucket, raw_object_key)
            content = response.read()
            response.close()
            response.release_conn()
            
            # 2. Extract locally
            ext = raw_object_key.split(".")[-1].lower() if "." in raw_object_key else ""
            extracted_text = ""
            quality = ExtractionQuality.HIGH
            
            if ext == "html" or ext == "htm":
                soup = BeautifulSoup(content, "lxml")
                for script in soup(["script", "style", "nav", "footer", "header"]):
                    script.extract()
                extracted_text = soup.get_text(separator="\n", strip=True)
                
            elif ext == "pdf":
                pdf_io = io.BytesIO(content)
                try:
                    extracted_text = pdfminer.high_level.extract_text(pdf_io)
                except Exception as e:
                    logger.error(f"PDFminer failed, fall back to direct string: {e}")
                    extracted_text = ""
                if len(extracted_text.strip()) < 50 and use_ocr:
                    quality = ExtractionQuality.LOW
                
            elif ext in ["png", "jpg", "jpeg"] and use_ocr:
                img = Image.open(io.BytesIO(content))
                extracted_text = pytesseract.image_to_string(img)
                quality = ExtractionQuality.MEDIUM
            else:
                try:
                    extracted_text = content.decode("utf-8", errors="ignore")
                except:
                    extracted_text = "[Binary Content Cannot Be Extracted]"
                quality = ExtractionQuality.LOW

            # Clean and trim
            if not extracted_text:
                extracted_text = "No extractable text found."

            # 3. LLM Enhancement (Optional - note using deeper model if specified but fallback to deepseek logic is in enrichment usually)
            if use_llm and len(extracted_text) > 10:
                try:
                    prompt = f"Read this raw text and convert into clean markdown with headers.\n\nRaw Text:\n{extracted_text[:3000]}"
                    resp = litellm.completion(
                        model="deepseek/deepseek-chat",
                        messages=[{"role": "user", "content": prompt}],
                        api_key=self.settings.model.primary_api_key
                    )
                    extracted_text = resp.choices[0].message.content
                except Exception as e:
                    logger.warning(f"LLM inline enhancement failed: {e}")

            # 4. Upload Extracted Text locally
            if "." in raw_object_key:
                new_key = raw_object_key.rsplit(".", 1)[0] + ".txt"
            else:
                new_key = raw_object_key + ".txt"
                
            if not self.minio_client.bucket_exists(ext_bucket):
                self.minio_client.make_bucket(ext_bucket)
                
            text_bytes = extracted_text.encode("utf-8")
            self.minio_client.put_object(
                ext_bucket,
                new_key,
                io.BytesIO(text_bytes),
                length=len(text_bytes),
                content_type="text/plain"
            )
            
            logger.info(f"Successfully stored unified extraction target: {new_key}")
            
            return {
                "success": True,
                "extracted_object_key": new_key,
                "quality": quality.value,
                "text_preview": extracted_text[:2000] # Send safe chunk back to workflow for inspection if needed
            }
        except Exception as e:
            logger.exception(f"Extraction localized process failure: {e}")
            return {"success": False, "error": str(e)}

    @activity.defn
    async def chunk_extracted_text(self, payload: dict) -> dict:
        """
        Splits extracted text into chunks for parallel or sequential LLM processing.
        Payload: extracted_object_key, chunk_size (optional)
        """
        object_key = payload["extracted_object_key"]
        chunk_size = payload.get("chunk_size", 15000) # Default ~15k chars
        bucket = self.settings.minio.bucket_extracted
        
        try:
            response = self.minio_client.get_object(bucket, object_key)
            text = response.read().decode("utf-8")
            response.close()
            response.release_conn()
            
            # Simple chunking by character count (better to use tokens or sentence boundaries in future)
            chunks = [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]
            
            return {
                "success": True,
                "chunks": chunks,
                "total_chunks": len(chunks)
            }
        except Exception as e:
            logger.error(f"Chunking failed for {object_key}: {e}")
            return {"success": False, "error": str(e)}

    @activity.defn
    async def enhance_text_chunk(self, payload: dict) -> dict:
        """
        Performs LLM-based cleaning/formatting on a single text chunk.
        """
        chunk_text = payload["chunk_text"]
        chunk_index = payload["chunk_index"]
        
        prompt = (
            "You are a medical data architect. Convert the following raw OCR/Text chunk into clean, structured markdown. "
            "Preserve all clinical values, dosages, and medical terms exactly. Do not summarize; just reformat and clean noise.\n\n"
            f"Raw Chunk:\n{chunk_text}"
        )
        
        try:
            resp = litellm.completion(
                model="deepseek/deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                api_key=self.settings.model.primary_api_key
            )
            enhanced = resp.choices[0].message.content
            return {"success": True, "enhanced_text": enhanced, "chunk_index": chunk_index}
        except Exception as e:
            logger.warning(f"Chunk enhancement failed for index {chunk_index}: {e}")
            return {"success": False, "error": str(e), "chunk_index": chunk_index}

    @activity.defn
    async def merge_enhanced_chunks(self, payload: dict) -> dict:
        """
        Merges multiple enhanced text chunks into a single document and updates MinIO.
        """
        chunks = payload["chunks"] # List of {"enhanced_text": "...", "chunk_index": 0}
        original_key = payload["original_key"]
        
        # Sort by index just in case
        sorted_chunks = sorted(chunks, key=lambda x: x["chunk_index"])
        full_text = "\n\n".join([c["enhanced_text"] for c in sorted_chunks if c.get("enhanced_text")])
        
        ext_bucket = self.settings.minio.bucket_extracted
        new_key = original_key # We overwrite or use a new suffix if needed
        
        try:
            text_bytes = full_text.encode("utf-8")
            self.minio_client.put_object(
                ext_bucket,
                new_key,
                io.BytesIO(text_bytes),
                length=len(text_bytes),
                content_type="text/plain"
            )
            return {"success": True, "object_key": new_key}
        except Exception as e:
            logger.error(f"Merging failed: {e}")
            return {"success": False, "error": str(e)}

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
                        from ks.domain.enums import DocumentStatus
                        doc.extracted_text_key = payload["extracted_object_key"]
                        doc.status = DocumentStatus.EXTRACTED # Propagate forward state
            
            await session.commit()

    @activity.defn
    async def verify_extraction_activity(self, payload: dict) -> dict:
        """
        Critic Agent: Reviews extracted facts against the source text to identify hallucinations.
        """
        facts = payload["facts"] # List of extracted facts (S-P-O + text)
        source_text = payload["source_text"]
        
        prompt = (
            "You are a clinical integrity auditor. Your job is to verify if the following extracted facts are accurately supported by the provided source text.\n\n"
            "SOURCE TEXT:\n"
            f"{source_text[:10000]}\n\n" # Limit source for token safety
            "EXTRACTED FACTS:\n"
            f"{json.dumps(facts, indent=2)}\n\n"
            "For each fact, determine if it is a hallucination or inaccurate. Provide a critique and suggested fix if needed.\n"
            "Return valid JSON: {\"verifications\": [{\"id\": \"fact_id\", \"is_hallucination\": false, \"confidence_score\": 0.95, \"critique\": \"...\", \"suggested_fix\": \"...\"}]}"
        )
        
        try:
            resp = litellm.completion(
                model="deepseek/deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                api_key=self.settings.model.primary_api_key
            )
            report = json.loads(resp.choices[0].message.content)
            return {"success": True, "report": report.get("verifications", [])}
        except Exception as e:
            logger.error(f"Verification activity failed: {e}")
            return {"success": False, "error": str(e)}
