import os
import httpx

API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000/api/v1")


async def get(path: str):
    async with httpx.AsyncClient() as client:
        return await client.get(f"{API_BASE}{path}")


async def post(path: str, data: dict):
    async with httpx.AsyncClient() as client:
        return await client.post(f"{API_BASE}{path}", json=data)
