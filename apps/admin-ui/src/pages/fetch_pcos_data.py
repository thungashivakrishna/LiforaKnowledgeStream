import asyncio
import httpx
import uuid
import sys

API_URL = "http://localhost:8000/api/v1"

CORES = [
    {
        "title": "Polycystic Ovary Syndrome (PCOS) Clinical Guide",
        "url": "https://en.wikipedia.org/wiki/Polycystic_ovary_syndrome"
    },
    {
        "title": "Endometriosis Pathophysiology and Guidelines",
        "url": "https://en.wikipedia.org/wiki/Endometriosis"
    },
    {
        "title": "Adenomyosis Diagnosis and Management",
        "url": "https://en.wikipedia.org/wiki/Adenomyosis"
    },
    {
        "title": "Insulin Resistance and Metabolic Dysfunction",
        "url": "https://en.wikipedia.org/wiki/Insulin_resistance"
    },
    {
        "title": "Spearmint Tea Effects on PCOS Hirsutism and Hormones",
        "url": "https://pubmed.ncbi.nlm.nih.gov/19585478/"
    }
]

async def main():
    async with httpx.AsyncClient(timeout=60.0) as client:
        # 1. Fetch available sources
        print("Fetching sources from database...")
        try:
            sources_res = await client.get(f"{API_URL}/sources")
            sources = sources_res.json()
            if isinstance(sources, dict) and "items" in sources:
                sources = sources["items"]
        except Exception as e:
            print(f"Failed to fetch sources: {e}")
            return

        if not sources:
            print("No sources found. Creating a new Medical source registry...")
            # Create a source
            source_payload = {
                "name": "Wikipedia Medical Library",
                "root_url": "https://en.wikipedia.org",
                "source_type": "KNOWLEDGE_BASE_SOURCE"
            }
            res = await client.post(f"{API_URL}/sources", json=source_payload)
            source = res.json()
            source_id = source["id"]
        else:
            source_id = sources[0]["id"]

        print(f"Using Source ID: {source_id}")

        for doc in CORES:
            print(f"\nRegistering document: {doc['title']}...")
            
            # Register Document
            register_payload = {
                "source_id": source_id,
                "title": doc["title"],
                "canonical_url": doc["url"]
            }
            
            try:
                # Add to registry (using a raw db execution or standard router if available)
                # Let's post to /acquisition/fetch directly if that auto-registers, 
                # or create document entries. Let's see if there is a document registration endpoint.
                # In typical cases, the API allows fetching directly.
                print(f"Spawning Acquisition & Extraction workflows for {doc['title']}...")
                
                # Create a document Registry entry via SQL direct insert or API if exists.
                # Since we don't have a direct POST /documents endpoint shown in router, 
                # let's run a quick query to insert them into Postgres directly.
                pass
            except Exception as e:
                print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
