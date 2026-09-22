"""pgvector menu search"""
import os
from supabase import Client
from typing import List, Dict
from app.db.supabase import get_supabase


async def search_menu(restaurant_id: str, query: str, limit: int = 5) -> List[Dict]:
    """Search menu items using pgvector similarity"""
    supabase: Client = get_supabase()
    
    # Generate embedding for query
    # TODO: Use text-embedding-3-small
    embedding = [0.0] * 1536  # Placeholder
    
    # Search pgvector
    result = supabase.rpc(
        "search_menu_items",
        {
            "restaurant_uuid": restaurant_id,
            "query_embedding": embedding,
            "match_count": limit,
        },
    ).execute()
    
    return result.data or []


async def sync_menu_embeddings(restaurant_id: str, menu_items: List[Dict]):
    """Generate and store embeddings for menu items"""
    # TODO: Batch generate embeddings and upsert to Supabase
    pass