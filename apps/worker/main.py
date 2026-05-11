import asyncio
import logging

import httpx
from minio import Minio
from temporalio.client import Client
from temporalio.worker import Worker
from qdrant_client import QdrantClient
from neo4j import GraphDatabase

from ks.config.settings import get_settings
from ks.discovery.activities import DiscoveryActivities
from ks.discovery.workflows import DiscoveryWorkflow
from ks.acquisition.activities import AcquisitionActivities
from ks.acquisition.workflows import AcquisitionWorkflow
from ks.extraction.activities import ExtractionActivities
from ks.extraction.workflows import ExtractionWorkflow
from ks.enrichment.activities import EnrichmentActivities
from ks.enrichment.workflows import EnrichmentWorkflow
from ks.chunking.activities import ChunkingActivities
from ks.chunking.workflows import ChunkingWorkflow
from ks.graph.activities import GraphActivities
from ks.graph.workflows import GraphSyncWorkflow
from ks.system.activities import SystemActivities
from ks.system.workflows import DocumentIngestionWorkflow

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main() -> None:
    settings = get_settings()
    
    # 1. Connect to Temporal
    client = await Client.connect(settings.temporal.address)
    
    # 2. Setup Activities
    minio_client = Minio(
        settings.minio.endpoint,
        access_key=settings.minio.access_key,
        secret_key=settings.minio.secret_key,
        secure=settings.minio.secure
    )
    
    async with httpx.AsyncClient(timeout=30.0) as http_client:
        discovery_activities = DiscoveryActivities(http_client)
        acquisition_activities = AcquisitionActivities(http_client, minio_client)
        extraction_activities = ExtractionActivities(minio_client)
        enrichment_activities = EnrichmentActivities(minio_client)
        system_activities = SystemActivities()
        
        qdrant_client = QdrantClient(
            host=settings.qdrant.host,
            port=settings.qdrant.port,
        )
        chunking_activities = ChunkingActivities(minio_client, qdrant_client)
        
        neo4j_driver = GraphDatabase.driver(
            settings.neo4j.uri,
            auth=(settings.neo4j.user, settings.neo4j.password)
        )
        graph_activities = GraphActivities(neo4j_driver)
        
        # 3. Create Worker
        worker = Worker(
            client,
            task_queue=settings.temporal.task_queue,
            workflows=[
                DiscoveryWorkflow, AcquisitionWorkflow, ExtractionWorkflow, 
                EnrichmentWorkflow, ChunkingWorkflow, GraphSyncWorkflow,
                DocumentIngestionWorkflow
            ],
            activities=[
                system_activities.prepare_stage_run,
                discovery_activities.discover_candidates,
                discovery_activities.persist_candidates,
                discovery_activities.finalize_discovery_run,
                acquisition_activities.fetch_content,
                acquisition_activities.audit_document_intelligence,
                acquisition_activities.persist_audit_facts,
                acquisition_activities.store_raw_artifact,
                acquisition_activities.update_fetch_status,
                extraction_activities.perform_full_extraction,
                extraction_activities.update_extraction_status,
                enrichment_activities.detect_relevant_frameworks,
                enrichment_activities.run_llm_enrichment,
                enrichment_activities.persist_enrichment_results,
                enrichment_activities.update_enrichment_status,
                chunking_activities.ensure_qdrant_collection,
                chunking_activities.fetch_text_and_metadata,
                chunking_activities.split_and_embed,
                chunking_activities.index_in_qdrant,
                chunking_activities.persist_chunk_metadata,
                chunking_activities.update_chunk_status,
                graph_activities.fetch_graph_data,
                graph_activities.sync_to_neo4j,
                graph_activities.update_graph_status,
            ],
        )
        
        logger.info("Starting Knowledge Stream worker on queue: %s", settings.temporal.task_queue)
        await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
