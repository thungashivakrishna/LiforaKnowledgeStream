import httpx
import asyncio

async def test_filters():
    async with httpx.AsyncClient() as client:
        # Test 1: No filters
        resp = await client.get("http://localhost:8000/api/v1/graph/explorer/data")
        print(f"No filters: {len(resp.json()['nodes'])} nodes")
        
        # Test 2: Search filter
        resp = await client.get("http://localhost:8000/api/v1/graph/explorer/data?q=Vitamin")
        print(f"Search 'Vitamin': {len(resp.json()['nodes'])} nodes")
        
        # Test 3: Type filter
        resp = await client.get("http://localhost:8000/api/v1/graph/explorer/data?type=Nutrient")
        print(f"Type 'Nutrient': {len(resp.json()['nodes'])} nodes")
        
        # Test 4: Framework filter
        resp = await client.get("http://localhost:8000/api/v1/graph/explorer/data?framework=Ayurveda")
        print(f"Framework 'Ayurveda': {len(resp.json()['nodes'])} nodes")

if __name__ == "__main__":
    asyncio.run(test_filters())
