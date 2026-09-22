"""Supabase client initialization"""
from supabase import create_client, Client
import os

_supabase: Client = None


def init_supabase():
    global _supabase
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if url and key:
        _supabase = create_client(url, key)
    return _supabase


def get_supabase() -> Client:
    if _supabase is None:
        init_supabase()
    return _supabase