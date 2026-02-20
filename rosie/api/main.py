import os
import time
import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Any

from ..agent.react_agent import ask
from ..collectors.runner import run_all
from ..storage.cache import save as save_cache, load as load_cache

logger = logging.getLogger(__name__)

app = FastAPI(title="Rosie API", version="1.0.0", description="AI-powered AWS environment visibility")

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    model: str = "rosie"
    messages: list[ChatMessage]
    stream: bool = False

class ChatChoice(BaseModel):
    index: int
    message: ChatMessage
    finish_reason: str

class ChatResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[ChatChoice]

class CollectRequest(BaseModel):
    region: str = "us-east-1"
    account_id: str = "000000000000"

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/v1/models")
def list_models():
    return {"object": "list", "data": [{"id": "rosie", "object": "model", "created": 0, "owned_by": "rosie"}]}

@app.post("/v1/chat/completions", response_model=ChatResponse)
def chat_completions(request: ChatRequest):
    user_messages = [m for m in request.messages if m.role == "user"]
    if not user_messages:
        raise HTTPException(status_code=400, detail="No user message found")
    question = user_messages[-1].content
    answer = ask(question)
    return ChatResponse(
        id=f"chatcmpl-{int(time.time())}",
        created=int(time.time()),
        model=request.model,
        choices=[ChatChoice(index=0, message=ChatMessage(role="assistant", content=answer), finish_reason="stop")],
    )

@app.post("/collect")
def trigger_collection(req: CollectRequest):
    resources = run_all(region=req.region, account_id=req.account_id)
    path = save_cache(resources)
    return {"collected": len(resources), "cache_path": str(path)}

@app.get("/inventory")
def get_inventory():
    resources = load_cache()
    return {"count": len(resources), "resources": resources[:100]}
