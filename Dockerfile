FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    build-essential \
    libpq-dev \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu torch torchvision
RUN pip install --no-cache-dir -r requirements.txt

# Pre-cache Docling models so the container works fast offline
# Pre-cache Docling models (layout, tables, OCR) so the container works offline and instantly
RUN python -c "import urllib.request; \
from docling.document_converter import DocumentConverter; \
from docling.datamodel.pipeline_options import PdfPipelineOptions; \
from docling.document_converter import PdfFormatOption, InputFormat; \
from io import BytesIO; \
from docling.datamodel.base_models import DocumentStream; \
pdf_url = 'https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf'; \
req = urllib.request.Request(pdf_url, headers={'User-Agent': 'Mozilla/5.0'}); \
pdf_bytes = urllib.request.urlopen(req).read(); \
pipeline_options = PdfPipelineOptions(); \
pipeline_options.do_ocr = True; \
pipeline_options.do_table_structure = True; \
converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)}); \
stream = DocumentStream(name='dummy.pdf', stream=BytesIO(pdf_bytes)); \
converter.convert(stream)"

# Copy source code
COPY src/ ./src/
COPY apps/ ./apps/
COPY infrastructure/seed/ ./infrastructure/seed/
COPY infrastructure/scripts/ ./infrastructure/scripts/
COPY pyproject.toml .
COPY alembic.ini .
COPY infrastructure/migrations/ ./infrastructure/migrations/

# Set Python path to include src
ENV PYTHONPATH=/app/src

# Default command for API
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
