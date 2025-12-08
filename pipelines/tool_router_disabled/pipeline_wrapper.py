from haystack.components.agents import Agent
from hayhooks import BasePipelineWrapper

class PipelineWrapper(BasePipelineWrapper):
    def setup(self):
        # Hayhooks constructs the pipeline from YAML and passes it here
        # self.pipeline is already set on the wrapper instance.
        assert self.pipeline is not None

        # Example: get the Agent if you want to add tools later
        agent: Agent = self.pipeline.get_component("router_agent")
        # TODO: add MCP tools to `agent` here

    async def run_api(self, request):
        result = self.pipeline.run(data={"messages": request.messages})
        return {"replies": result["replies"]}

    async def run_chat_completion(self, model, messages, body):
        result = self.pipeline.run(data={"messages": messages})
        reply = result["replies"][-1]
        content = reply["content"] if isinstance(reply, dict) else reply
        return {
            "id": "chatcmpl-hayhooks-tool-router",
            "object": "chat.completion",
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {
                        "role": "assistant",
                        "content": content,
                    },
                }
            ],
        }

