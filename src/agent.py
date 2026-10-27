import argparse
import os
import sqlite3

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain.agents.middleware import SummarizationMiddleware, wrap_tool_call
from langchain.chat_models import init_chat_model
from langchain_core.messages.utils import count_tokens_approximately
from langfuse import get_client
from langfuse.langchain import CallbackHandler
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Checkpointer

from tools import TOOLS

load_dotenv()

SYSTEM = """
You are agent-chef who is an expert in food compound.
Your main goal is to find the available products for user who can't eat.

MAIN RULE:
You cant't find the products by yourself. You must use the tool to find it.
You cant't give any recommendations without tool calling.
if you don't know the answer from tool, do not write any answer.
"""

DB_PATH = "product.db"


def chat_model(size: str = "cheap", **kwargs):
    """A model object for the configured provider. A dozen lines, copy them once."""
    name = os.environ[f"MODEL_{size.upper()}"]  # ids live in .env, never in code
    secret = os.environ["LLM_API_KEY"]
    if os.getenv("LLM_REASONING_EFFORT"):  # gpt-5.x: tools need reasoning "none"
        kwargs.setdefault("reasoning_effort", os.environ["LLM_REASONING_EFFORT"])
    # Gemini over OpenAI-compat drops the reasoning signature: turn two 400s
    if os.getenv("LLM_PROVIDER", "openai_compat") == "google_genai":
        return init_chat_model(f"google_genai:{name}", api_key=secret, **kwargs)
    return init_chat_model(
        f"openai:{name}", api_key=secret, base_url=os.environ["LLM_BASE_URL"], **kwargs
    )


@wrap_tool_call
def log_tool_call(request, handler):
    print(f"[tool] {request.tool_call['name']}({request.tool_call['args']})")
    return handler(request)


def memory_middlewares(memory: str) -> list:
    if memory == "buffer":
        return []
    # a model object, not an id string: a bare id would bypass base_url and the key
    return [
        SummarizationMiddleware(
            chat_model("cheap"), trigger=("messages", 15), keep=("messages", 8)
        )
    ]


def build_agent(checkpointer: Checkpointer, middlewares: list) -> CompiledStateGraph:
    return create_agent(
        chat_model("cheap"),
        TOOLS,
        system_prompt=SYSTEM,
        middleware=[log_tool_call, *middlewares],
        checkpointer=checkpointer,
    )


def ask(agent: CompiledStateGraph, thread_id: str, question: str) -> dict:
    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": 10,
        "callbacks": [CallbackHandler()],  # fresh per turn: one trace per invoke
    }
    result = agent.invoke({"messages": [{"role": "user", "content": question}]}, config)
    get_client().flush()
    return result


def run(thread_id: str, memory: str) -> None:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    agent = build_agent(SqliteSaver(conn), memory_middlewares(memory))
    try:
        while (question := input("you> ").strip()) != "exit":
            messages = ask(agent, thread_id, question)["messages"]
            print(f"agent> {messages[-1].content}")
            print(f"[state] {len(messages)} messages, ~{count_tokens_approximately(messages)} tokens")
    except EOFError:
        pass
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--thread-id", default="product-db")
    parser.add_argument("--memory", choices=["summary", "buffer"], default="summary")
    args = parser.parse_args()
    run(args.thread_id, args.memory)
