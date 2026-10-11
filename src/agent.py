import operator
import os
import re
import sys

from langchain.agents import create_agent
from langchain.agents.middleware import wrap_tool_call
from langchain.chat_models import init_chat_model

from db import PRODUCTS
from dotenv import load_dotenv
from openai import OpenAI
from langgraph.graph import StateGraph, START, END, MessagesState
from langgraph.prebuilt import ToolNode
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langfuse import get_client
from langfuse.langchain import CallbackHandler
from langchain.chat_models import init_chat_model
from tools import TOOLS, print_schemas

load_dotenv()

MODEL = os.environ["MODEL_CHEAP"]

# TODO 1. Tool name, call format; the STOP rule stays separate
SYSTEM = """
You are agent-chef who is an expert in food compound. 
Your main goal is to find the available products for user who can't eat.

MAIN RULE:
You cant't find the products by yourself. You must use the tool to find it.
You cant't give any recommendations without tool calling. 
if you don't know the answer from tool, do not write any answer.
"""


QUESTION = "I avoid gluten and lactose. Can I eat oat milk? If not, what else can I eat?"


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

agent = create_agent(chat_model("cheap"), TOOLS, system_prompt=SYSTEM, middleware=[log_tool_call])

result = agent.invoke(
    {
        "messages": [
            {"role": "user", "content": QUESTION},
        ],
    },
    config={"recursion_limit": 8, "callbacks": [CallbackHandler()]},
)
get_client().flush()

print_schemas()

for m in result["messages"]:
    m.pretty_print()
