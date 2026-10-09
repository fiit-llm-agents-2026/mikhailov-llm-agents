import operator
import os
import re
import sys

from db import PRODUCTS
from dotenv import load_dotenv
from openai import OpenAI
from langgraph.graph import StateGraph, START, END, MessagesState
from langgraph.prebuilt import ToolNode
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langfuse import get_client
from langfuse.langchain import CallbackHandler

load_dotenv()

MODEL = os.environ["MODEL_CHEAP"]

# TODO 1. Tool name, call format; the STOP rule stays separate
SYSTEM = """
You are agent-chef who is an expert in gluten, lactose food compound. 
Your main goal is to find the available products for user who can't eat.

MAIN RULE:
You cant't find the products by yourself. You must use the tool to find it.
You cant't give any recommendations without tool calling. 
if you don't know the answer from tool, do not write any answer.
"""


QUESTION = "Can I eat qenuia if I avoid gluten and lactose? \n"


@tool
def gluten_free(id: str) -> str:
    """Returns the answer for the question: "Is this product gluten free?"
       Takes id from tool find_product_by_name
     Args:
     id: product_id in PRODUCT database

     Returns:
         - "Yes" if this product is gluten free
         - "No" if this product isn't gluten free
         - "Don't know" if this product isn't in database
    """

    product = PRODUCTS.get(id, None)
    if not product:
        return "Don't know"
    return "Yes" if product["gluten_free"] else "No"


@tool
def lactose_free(id: str) -> str:
    """Returns the answer for the question: "Is this product lactose free?"
       Takes id from tool find_product_by_name
     Args:
     id: product_id in PRODUCT database

     Returns:
         - "Yes" if this product is lactose free
         - "No" if this product isn't lactose free
         - "Don't know" if this product isn't in database
    """
    product = PRODUCTS.get(id, None)
    if not product:
        return "Don't know"
    return "Yes" if product["lactose_free"] else "No"


@tool
def find_product_by_name(product_name: str) -> str:
    """Use it when you want tot find the product by name.
     Args:
     product_name: name of the product in database

     Returns:
        Returns the id of the product from database
        if there is no product -> returns Unknown product {product_name}. Known products: {all_names}.
    """
    all_names = [product["name"] for product in PRODUCTS.values()]
    for id, db_product in PRODUCTS.items():
        if db_product["name"].strip().lower() == product_name.strip().lower():
            return id
    return f"Unknown product {product_name!r}. Known products: {all_names}."


def should_continue(state: MessagesState) -> str:
    last = state["messages"][-1]
    if last.tool_calls:
        return "tools"
    return END


def call_model(state: MessagesState) -> dict:
    # Return the delta. A whole list here appends history to history.
    return {"messages": [bound.invoke(state["messages"])]}


tools = [gluten_free, find_product_by_name, lactose_free]

llm = ChatOpenAI(
    model=MODEL,
    api_key=os.environ["LLM_API_KEY"],
    base_url=os.environ["LLM_BASE_URL"],
)

bound = llm.bind_tools(tools)

builder = StateGraph(MessagesState)
builder.add_node("model", call_model)
builder.add_node("tools", ToolNode(tools))
builder.add_edge(START, 'model')
builder.add_edge("tools", "model")
builder.add_conditional_edges("model", should_continue, ["tools", END])

manual = builder.compile()
print(manual.get_graph().draw_mermaid())

result = manual.invoke(
    {"messages":
        [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": QUESTION}
        ],
    },
    config={"recursion_limit": 8, 'callbacks': [CallbackHandler()]},
)
get_client().flush()


for m in result["messages"]:
    m.pretty_print()