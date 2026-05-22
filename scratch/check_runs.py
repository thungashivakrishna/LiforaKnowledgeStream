import sys
import os
sys.path.append("/app")
sys.path.append("/app/src")

import asyncio
from sqlalchemy import select
from apps.api.database import AsyncSessionFactory
from ks.domain.models import CandidateDiscoveryRun, CandidateDocumentEvaluation, DocumentRegistry

async def check_database_status():
    async with AsyncSessionFactory() as session:
        # Check Runs
        print("=== CANDIDATE DISCOVERY RUNS ===")
        runs_res = await session.execute(select(CandidateDiscoveryRun))
        runs = runs_res.scalars().all()
        for r in runs:
            print(f"- Run ID: {r.id}\n  Status: {r.status}\n  Candidate Count: {r.candidate_count}\n  Error: {r.error_message}\n  Completed At: {r.completed_at}\n")
            
        # Check Evaluations Count
        evals_res = await session.execute(select(CandidateDocumentEvaluation))
        evals = evals_res.scalars().all()
        print(f"Total Evaluations Found: {len(evals)}")
        
        # Check Document Registry Count
        docs_res = await session.execute(select(DocumentRegistry))
        docs = docs_res.scalars().all()
        print(f"Total Registered Documents: {len(docs)}")
        
        # Print a few registered documents
        print("\n=== SAMPLE REGISTERED DOCUMENTS ===")
        for d in docs[:10]:
            print(f"- Title: {d.title or 'N/A'}\n  URL: {d.canonical_url}\n  Source ID: {d.source_id}")

if __name__ == "__main__":
    asyncio.run(check_database_status())
