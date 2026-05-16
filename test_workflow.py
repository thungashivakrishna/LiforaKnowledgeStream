import asyncio
import httpx
import time

async def run_test():
    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        # 1. Create Filter Profile
        print("Creating Filter Profile for PCOS...")
        profile_res = await client.post("/api/v1/discovery/profiles", json={
            "name": "PCOS Intent Focus",
            "mode": "FOCUSED",
            "topics": ["PCOS"],
            "max_candidates": 10
        })
        
        if profile_res.status_code != 200:
            print(f"Failed to create profile: {profile_res.text}")
            return
            
        profile_id = profile_res.json()["id"]
        print(f"Created Profile: {profile_id}")
        
        # 2. Trigger Run
        print("Triggering Discovery Run...")
        run_res = await client.post("/api/v1/discovery/runs", json={
            "mode": "FOCUSED",
            "filter_profile_id": profile_id,
            "source_ids": [],
            "framework_scope": []
        })
        
        if run_res.status_code != 200:
            print(f"Failed to start run: {run_res.text}")
            return
            
        run_id = run_res.json()["id"]
        print(f"Started Run: {run_id}")
        
        # 3. Poll for results
        print("Waiting for candidates to populate...")
        for i in range(20):
            await asyncio.sleep(5)
            status_res = await client.get(f"/api/v1/discovery/runs/{run_id}")
            if status_res.status_code == 200:
                data = status_res.json()
                print(f"[{i}] Status: {data['status']}, Candidates Discovered: {len(data['candidates'])}")
                if data['status'] in ["COMPLETED", "FAILED"] and len(data['candidates']) > 0:
                    print("Test successful! Candidates found:")
                    for c in data['candidates']:
                        print(f"- {c['title']} (Score: {c['score']}) -> {c['decision']}")
                    return
            else:
                print(f"Status check failed: {status_res.text}")

if __name__ == "__main__":
    asyncio.run(run_test())
