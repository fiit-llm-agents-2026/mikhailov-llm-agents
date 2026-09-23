import os
import re
import sys

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

ACTION_RE = re.compile(r"<action>\s*(\w+)\s*\((.*?)\)\s*</action>", re.DOTALL)
OBSERVATION_RE = re.compile(r"<observation>\s*(.*?)\s*</observation>", re.DOTALL)

client = OpenAI(api_key=os.environ["LLM_API_KEY"], base_url=os.environ["LLM_BASE_URL"])
MODEL = os.environ["MODEL_CHEAP"]

# TODO 1. Tool name, call format; the STOP rule stays separate
SYSTEM = """
You are agent-chef who is an expert in gluten food compound. 
Your main goal is to find the available products for user who can't eat gluten.

Your cant't find the products by yourself. You must use the tool to find it.
Only one tool is available. Tool can't work with any product. He has his own database of products with gluten.
1. name: gluten_free()
2. arguments: [product_name]
3. returns: 
    - "Yes" if this product is gluten free
    - "No" if this product isn't gluten free
    - "Don't know" if this product isn't in database

Work in cycle:
<thought>what can I offer to user at this step</thought>
<action>gluten_free("bread")</action>
<observation>Yes | No | Don't know</observation>

when the answer is ready - send it to user with message:
"Final answer: I found a good product for you - <product_name>"
 
Rules:
- don't do extra call during cycle. Exactly once
"""


STOP_RULE = "\nAfter the Action line STOP and wait: never write the Observation yourself."
QUESTION = "What can I eat without gluten? \n"


def gluten_free(product_name: str) -> str:
    db = [
        {"id": 2, "product_name": "bread", "is_gluten_free": False},
        {"id": 3, "product_name": "flour", "is_gluten_free": False},
        {"id": 4, "product_name": "buckwheat", "is_gluten_free": True},
        {"id": 5, "product_name": "quinoa", "is_gluten_free": True},
        {"id": 6, "product_name": "millet", "is_gluten_free": True},
        {"id": 7, "product_name": "amaranth", "is_gluten_free": True},
        {"id": 8, "product_name": "teff", "is_gluten_free": True},
        {"id": 9, "product_name": "sorghum", "is_gluten_free": True},
        {"id": 10, "product_name": "tapioca", "is_gluten_free": True},
        {"id": 11, "product_name": "cassava flour", "is_gluten_free": True},
        {"id": 12, "product_name": "arrowroot", "is_gluten_free": True},
        {"id": 13, "product_name": "chickpea flour", "is_gluten_free": True},
        {"id": 14, "product_name": "polenta", "is_gluten_free": True},
        {"id": 15, "product_name": "corn tortilla", "is_gluten_free": True},
        {"id": 16, "product_name": "rice noodles", "is_gluten_free": True},
        {"id": 17, "product_name": "glass noodles", "is_gluten_free": True},
        {"id": 18, "product_name": "rice paper", "is_gluten_free": True},
        {"id": 19, "product_name": "tamari", "is_gluten_free": True},
        {"id": 20, "product_name": "psyllium husk", "is_gluten_free": True},
        {"id": 21, "product_name": "sago", "is_gluten_free": True},
        {"id": 22, "product_name": "soy sauce", "is_gluten_free": False},
        {"id": 23, "product_name": "couscous", "is_gluten_free": False},
        {"id": 24, "product_name": "bulgur", "is_gluten_free": False},
        {"id": 25, "product_name": "semolina", "is_gluten_free": False},
        {"id": 26, "product_name": "spelt", "is_gluten_free": False},
        {"id": 27, "product_name": "seitan", "is_gluten_free": False},
        {"id": 28, "product_name": "orzo", "is_gluten_free": False},
        {"id": 29, "product_name": "barley malt", "is_gluten_free": False},
    ]
    for db_product in db:
        if db_product["product_name"] == product_name:
            return "Yes" if db_product["is_gluten_free"] else "No"
    return "Don't know"


TOOL = gluten_free


def parse_action(text: str) -> str | None:
    match = ACTION_RE.search(text)
    if match is None:
        return None
    return match.group(2).strip().strip('"\'')


def cut_at_observation(text: str) -> str:
    marker = text.find("<observation>")
    return text if marker == -1 else text[:marker].rstrip()


def run(honest: bool = True, steps: int = 5) -> list[str]:
    messages = [{"role": "system", "content": SYSTEM + (STOP_RULE if honest else "")},
                {"role": "user", "content": QUESTION}]
    transcript = [f"Question: {QUESTION}"]
    for _ in range(steps):
        answer = client.chat.completions.create(
            # pre-set high: hidden reasoning is billed from this budget too
            model=MODEL, messages=messages, max_completion_tokens=2000
        )
        choice = answer.choices[0]
        reply = choice.message.content or ""
        # a budget bug, not a parser bug: name it
        if not reply and choice.finish_reason == "length":
            raise RuntimeError(
                "Empty reply at the length limit: the budget went on hidden "
                "reasoning, not on your parser. Raise max_completion_tokens."
            )
        if honest:
            reply = cut_at_observation(reply)
        transcript.append(reply)
        print(reply)

        argument = parse_action(reply)
        if argument is None:
            break
        observation = f"Observation: {TOOL(argument)}"
        transcript.append(observation)
        print(observation)
        messages.append({"role": "assistant", "content": reply})
        messages.append({"role": "user", "content": observation})
    return transcript


if __name__ == "__main__":
    # --break removes both safeties: the second transcript you commit
    run(honest="--break" not in sys.argv)