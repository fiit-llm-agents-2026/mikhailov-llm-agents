import hashlib
import json
from typing import Literal

from langchain.tools import ToolRuntime, tool
from pydantic import BaseModel


class Profile(BaseModel):
    name: str | None = None
    gluten_free: bool | None = None
    lactose_free: bool | None = None
    vegan: bool | None = None


@tool
def save_memory(
    text: str,
    runtime: ToolRuntime,
    kind: Literal["semantic", "episodic", "procedural"] = "semantic",
) -> str:
    """Remember one explicitly stated user fact, event or standing instruction.

    Store one fact per call. Repeating identical text updates the same memory.
    """
    text = text.strip()
    if not text:
        raise ValueError("cannot save an empty user memory")
    key = hashlib.sha256(text.casefold().encode()).hexdigest()
    runtime.store.put(
        (runtime.context.user_id, "memories"), key, {"text": text, "kind": kind}
    )
    return "Memory saved."


@tool
def search_memories(query: str, runtime: ToolRuntime) -> str:
    """Find this user's saved facts by case-insensitive words; empty query lists all.

    This is lexical search, not semantic vector search.
    """
    terms = query.casefold().split()
    items = runtime.store.search((runtime.context.user_id, "memories"), limit=10000)
    matches = [
        item.value
        for item in items
        if all(term in item.value["text"].casefold() for term in terms)
    ]
    return json.dumps(matches, ensure_ascii=False)
