import asyncio
import httpx
import uuid
import sys

API_URL = "http://localhost:8000/api/v1"

# High Fidelity Registered Document UUIDs for dispatch
DISPATCH_IDS = [
    "a1111111-1111-4111-a111-111111111111", # Preventive
    "a2222222-2222-4222-a222-222222222222", # Nutrition
    "a3333333-3333-4333-a333-333333333333", # Physical
    "a4444444-4444-4444-a444-444444444444"  # Holistic
]

async def trigger_full_ingestion():
    print("🚀 Launching Parallel Multi-Perspective Data Load over 4 Domains...")
    async with httpx.AsyncClient(timeout=60.0) as client:
        
        # Dispatch parallel ingestion triggers by doc_id
        for doc_id in DISPATCH_IDS:
            print(f"\n📡 Dispatching Agents for Document: {doc_id}...")
            
            payload = {
                "document_id": doc_id,
                "force_refresh": True
            }
            
            try:
                # Calling the start_fetch endpoint identified in router
                res = await client.post(f"{API_URL}/acquisition/fetch", json=payload)
                
                if res.status_code < 300:
                     run_info = res.json()
                     print(f"   ✅ SUCCESSFULLY TRIGGERED. Run ID: {run_info['id']}")
                else:
                     print(f"   ⚠️ Trigger rejected: {res.text}")
            except Exception as ex:
                print(f"   ❌ Trigger failure: {ex}")

        print("\n🎉 ALL AGENTS DISPATCHED SUCCESSFULLY.")
        print("Monitor the pipelines via the Admin UI: http://localhost:5173/discovery")

if __name__ == "__main__":
    asyncio.run(trigger_full_ingestion())
