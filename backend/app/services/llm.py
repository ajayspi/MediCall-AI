"""GPT-4.1 medical dialogue integration with function calling.

The system prompt and the MEDICAL_FUNCTIONS schema (single source of truth)
live in app/services/agent_logic.py (stdlib, unit-tested); this module only
owns the OpenAI call. Imports stay third-party — verified via source checks on
this PC, exercised live in Docker/CI.
"""
import os
from typing import Any, Dict, List

import openai

from app.services.agent_logic import MEDICAL_FUNCTIONS, system_prompt

client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))


async def generate_response(
    messages: List[Dict[str, str]],
    clinic_name: str = "",
    ai_instructions: str = "",
    language: str = "hi",
    state: str = "GREETING",
    date: str = "",
    time: str = "",
    call_summary: str = "",
) -> Any:
    """Generate a medical dialogue response with medical function calling."""
    prompt = system_prompt(
        clinic_name=clinic_name,
        ai_instructions=ai_instructions,
        language=language,
        date=date,
        time=time,
        state=state,
        call_summary=call_summary,
    )
    response = await client.chat.completions.create(
        model="gpt-4.1",
        messages=[{"role": "system", "content": prompt}] + messages,
        functions=MEDICAL_FUNCTIONS,
        function_call="auto",
        temperature=0.1,
        max_tokens=500,
    )
    return response.choices[0].message