import sys
import os
import uuid
import random
sys.path.append("/app")
sys.path.append("/app/src")

import asyncio
import httpx
from sqlalchemy import select
from apps.api.database import AsyncSessionFactory
from ks.domain.models import SourceRegistry
from ks.domain.enums import SourceApprovalStatus
from ks.discovery.activities import DiscoveryActivities

async def run_diagnostics():
    print("====================================================")
    print("🧪 RUNNING TRUST REGISTRY & AUTOCACHE DIAGNOSTICS")
    print("====================================================")
    
    async with httpx.AsyncClient() as http_client:
        activities = DiscoveryActivities(http_client)
        
        # 1. Test Static Trusted Authority Rules
        print("\n[TEST 1] Testing Static Rule Auto-Approval for .gov...")
        gov_res = await activities.evaluate_source_authority({
            "domain": "clinicaltrials.gov",
            "snippet": "National Institutes of Health trials repository."
        })
        print(f"Result: {gov_res}")
        if gov_res.get("success") and gov_res.get("evaluation", {}).get("is_reputable"):
            print("✅ SUCCESS: .gov domain was auto-approved via static authority rules.")
        else:
            print("❌ FAILED: .gov domain was not approved.")
            
        print("\n[TEST 2] Testing Static Rule Auto-Approval for major journal...")
        journal_res = await activities.evaluate_source_authority({
            "domain": "academic.oup.com",
            "snippet": "Oxford University Press journals publishing endocrine research."
        })
        print(f"Result: {journal_res}")
        if journal_res.get("success") and journal_res.get("evaluation", {}).get("is_reputable"):
            print("✅ SUCCESS: academic.oup.com was auto-approved via static authority rules.")
        else:
            print("❌ FAILED: academic.oup.com was not approved.")

        # 2. Test Static Blocklist Rules
        print("\n[TEST 3] Testing Static Rule Auto-Rejection for spam TLD...")
        spam_res = await activities.evaluate_source_authority({
            "domain": "cheap-pcos-supplements.xyz",
            "snippet": "Buy cheap vitamins and quick weight loss pills here."
        })
        print(f"Result: {spam_res}")
        if spam_res.get("success") and not spam_res.get("evaluation", {}).get("is_reputable"):
            print("✅ SUCCESS: .xyz domain was auto-blocked via static rules.")
        else:
            print("❌ FAILED: .xyz domain was not blocked.")

        # 3. Test Dynamic Persistence Caching
        rand_suffix = random.randint(1000, 9999)
        test_domain = f"high-authority-medical-hub-{rand_suffix}.gov"
        print(f"\n[TEST 4] Testing Auto-Persistence and Caching for new domain: {test_domain}")
        
        # A. First check (should run static rules and persist to DB)
        print("First evaluation (not in DB yet)...")
        eval1 = await activities.evaluate_source_authority({
            "domain": test_domain,
            "snippet": "Official municipal health advisory board database."
        })
        print(f"First Eval Result: {eval1}")
        
        # B. Verify it was written to PostgreSQL
        print("Querying PostgreSQL to confirm persistence...")
        async with AsyncSessionFactory() as session:
            res = await session.execute(
                select(SourceRegistry).where(SourceRegistry.root_url == f"https://{test_domain}")
            )
            source_record = res.scalars().first()
            if source_record:
                print(f"✅ SUCCESS: Domain {test_domain} was auto-persisted in DB!")
                print(f"   Name: {source_record.name}, Approval Status: {source_record.approval_status.value}, Score: {source_record.authority_score}")
            else:
                print("❌ FAILED: Domain was not found in the database registry.")
                
        # C. Second check (should run DB lookup and bypass LLM/static calculation)
        print("Second evaluation (should pull from DB)...")
        eval2 = await activities.evaluate_source_authority({
            "domain": test_domain,
            "snippet": "Same municipal health advisory board database."
        })
        print(f"Second Eval Result: {eval2}")
        reason = eval2.get("evaluation", {}).get("reason", "")
        if "resolved from trust registry" in reason:
            print("✅ SUCCESS: Second evaluation retrieved status from DB cache successfully!")
        else:
            print("❌ FAILED: Second evaluation did not resolve from the DB cache.")

    print("\n====================================================")
    print("🏁 TRUST REGISTRY DIAGNOSTICS COMPLETED")
    print("====================================================")

if __name__ == "__main__":
    asyncio.run(run_diagnostics())
