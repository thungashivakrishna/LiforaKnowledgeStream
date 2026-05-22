import sys
import os
sys.path.append("/app")
sys.path.append("/app/src")

import asyncio
import httpx
import uuid
from sqlalchemy import select
from apps.api.database import AsyncSessionFactory
from ks.domain.models import DiscoveryFilterProfile
from ks.domain.enums import Framework, DiscoveryMode

API_URL = "http://localhost:8000/api/v1"

FRAMEWORKS_METADATA = {
    "EVIDENCE_BASED_WESTERN_MEDICINE": {
        "name": "Western Medicine",
        "topics": ["cardiovascular", "metabolic", "inflammatory", "oncology", "preventive_care", "clinical_guidelines"],
        "max_candidates": 20
    },
    "NUTRITION_SCIENCE": {
        "name": "Nutrition Science",
        "topics": ["macronutrients", "micronutrients", "dietary_patterns", "gut_health", "supplementation"],
        "max_candidates": 20
    },
    "PHYSICAL_ACTIVITY_SCIENCE": {
        "name": "Physical Activity",
        "topics": ["strength_training", "cardiovascular_exercise", "mobility", "recovery", "exercise_physiology"],
        "max_candidates": 20
    },
    "HOLISTIC_TRADITIONAL_SYSTEMS": {
        "name": "Holistic Traditional Systems",
        "topics": ["ayurveda", "yoga", "traditional_medicine", "seasonal_living", "mind_body"],
        "max_candidates": 20
    },
    "LIFESTYLE_BEHAVIORAL_HEALTH": {
        "name": "Lifestyle & Behavioral Health",
        "topics": ["sleep", "stress_management", "habit_formation", "adherence", "mental_health"],
        "max_candidates": 20
    },
    "PREVENTIVE_MEDICINE": {
        "name": "Preventive Medicine",
        "topics": ["screening_guidelines", "vaccination_schedules", "chronic_disease_prevention", "early_detection"],
        "max_candidates": 20
    },
    "DIAGNOSTICS_AND_LABS": {
        "name": "Diagnostics & Labs",
        "topics": ["biomarkers", "reference_intervals", "lab_testing", "radiology", "blood_chemistry"],
        "max_candidates": 20
    },
    "PHARMACOLOGY_MEDICINE": {
        "name": "Pharmacology Medicine",
        "topics": ["pharmacokinetics", "drug_interactions", "contraindications", "dosages", "prescription_guidelines"],
        "max_candidates": 20
    }
}

async def ensure_profile_exists(client: httpx.AsyncClient, framework_key: str, metadata: dict) -> str:
    profile_name = f"Test Profile - {metadata['name']}"
    
    # Query database to see if profile already exists
    async with AsyncSessionFactory() as session:
        res = await session.execute(
            select(DiscoveryFilterProfile).where(DiscoveryFilterProfile.name == profile_name)
        )
        existing = res.scalar_one_or_none()
        if existing:
            print(f"  Existing Profile found: '{profile_name}' (ID: {existing.id})")
            return str(existing.id)

    # If it doesn't exist, create it via API
    print(f"  Creating Profile: '{profile_name}'...")
    resp = await client.post(f"{API_URL}/discovery/profiles", json={
        "name": profile_name,
        "mode": "FOCUSED",
        "topics": metadata["topics"],
        "frameworks": [framework_key],
        "max_candidates": metadata["max_candidates"],
        "per_source_limit": metadata["max_candidates"]
    })
    
    if resp.status_code != 200:
        raise ValueError(f"Failed to create profile: {resp.text}")
        
    profile_id = resp.json()["id"]
    print(f"  Successfully Created Profile: {profile_id}")
    return profile_id

async def start_runs():
    print("====================================================")
    print("🚀 INITIALIZING MULTI-FRAMEWORK TEST RUNS (8 DOMAINS)")
    print("====================================================")

    async with httpx.AsyncClient(timeout=30.0) as client:
        active_runs = []
        
        for fw_key, fw_meta in FRAMEWORKS_METADATA.items():
            print(f"\n👉 Setting up Framework: {fw_key} ({fw_meta['name']})...")
            try:
                # 1. Ensure Discovery Filter Profile exists
                profile_id = await ensure_profile_exists(client, fw_key, fw_meta)
                
                # 2. Trigger Discovery Run
                print(f"  Triggering Discovery Run for {fw_meta['name']}...")
                run_resp = await client.post(f"{API_URL}/discovery/runs", json={
                    "mode": "FOCUSED",
                    "filter_profile_id": profile_id,
                    "source_ids": [],
                    "framework_scope": [fw_key]
                })
                
                if run_resp.status_code != 200:
                    print(f"  ❌ Failed to start run: {run_resp.text}")
                    continue
                    
                run_data = run_resp.json()
                run_id = run_data["id"]
                print(f"  ✅ SUCCESS! Started Run ID: {run_id}")
                
                active_runs.append({
                    "framework": fw_key,
                    "name": fw_meta["name"],
                    "run_id": run_id,
                    "status": "RUNNING",
                    "candidate_count": 0
                })
                
                # Stagger the triggers by 3 seconds to avoid DuckDuckGo request collisions
                await asyncio.sleep(3.0)
                
            except Exception as e:
                print(f"  ❌ Exception during setup: {e}")

        # 3. Monitor active runs
        print("\n====================================================")
        print("📊 MONITORING RUN STATUSES (POLLING EVERY 15 SECONDS)")
        print("====================================================")
        
        for i in range(12): # Poll for up to 3 minutes
            await asyncio.sleep(15.0)
            all_completed = True
            print(f"\n--- [Poll {i+1}/12] Progress Update ---")
            
            for run in active_runs:
                if run["status"] in ["COMPLETED", "FAILED"]:
                    print(f"- {run['name']}: {run['status']} (Candidates: {run['candidate_count']})")
                    continue
                    
                # Fetch fresh status
                try:
                    resp = await client.get(f"{API_URL}/discovery/runs/{run['run_id']}")
                    if resp.status_code == 200:
                        data = resp.json()
                        run["status"] = data["status"]
                        run["candidate_count"] = len(data["candidates"])
                        print(f"- {run['name']}: {run['status']} (Candidates Found: {run['candidate_count']})")
                        if run["status"] not in ["COMPLETED", "FAILED"]:
                            all_completed = False
                    else:
                        print(f"- {run['name']}: ERROR checking status")
                        all_completed = False
                except Exception as ex:
                    print(f"- {run['name']}: Exception checking status: {ex}")
                    all_completed = False
            
            if all_completed:
                print("\n🎉 All framework runs completed discovery phase!")
                break

        print("\n====================================================")
        print("🏁 MULTI-FRAMEWORK TEST RUN LAUNCH COMPLETED")
        print("====================================================")

if __name__ == "__main__":
    asyncio.run(start_runs())
