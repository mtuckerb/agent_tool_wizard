from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import json
import os
import logging
from hayhooks import BasePipelineWrapper
from hayhooks.settings import settings

logger = logging.getLogger(__name__)

class Message(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: List[Message]

class PipelineWrapper(BasePipelineWrapper):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def setup(self):
        # Basic setup without using Haystack pipeline for now
        logger.info("Router pipeline setup complete - using simple echo mode")

    async def run_api(self, request: ChatRequest) -> Dict[str, Any]:
        # Simple echo for now
        user_message = ""
        if request.messages and len(request.messages) > 0:
            user_message = request.messages[-1].content
        
        # Return proper format with Haystack-like replies
        return {
            "replies": [
                {
                    "role": "assistant",
                    "content": f"Router received: {user_message}",
                    "meta": {"source": "api"}
                }
            ]
        }

    async def run_chat_completion(self, model: str, messages: List[dict], body: dict) -> Dict[str, Any]:
        # Simple echo for now
        user_message = ""
        if messages and len(messages) > 0:
            last_message = messages[-1]
            if isinstance(last_message, dict):
                user_message = last_message.get("content", "")
        
        response_content = f"Router received: {user_message}"
        
        # Return Haystack-standard format for chat completion
        return {
            "replies": [
                {
                    "role": "assistant", 
                    "content": response_content,
                    "meta": {"model": model}
                }
            ]
        }
