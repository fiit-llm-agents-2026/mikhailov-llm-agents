import json
import random

from langchain_core.tools import tool
from langchain_core.utils.function_calling import convert_to_openai_tool
from db import PRODUCTS


@tool(parse_docstring=True)
def food_search(
    gluten_free: bool | None = None,
    lactose_free: bool | None = None,
    vegan: bool | None = None
) -> str:
    """
    Search for products based on gluten and lactose free criteria.

    Args:
        gluten_free (bool): Whether the product should be gluten-free.
        lactose_free (bool): Whether the product should be lactose-free.
        vegan (bool): Whether the product should be vegan.

    Returns:
        str: A string containing the names of products that match the criteria.
    """
    answer = []

    for product in PRODUCTS.values():
        gluten_flag = gluten_free is None or product["gluten_free"] == gluten_free
        lactose_flag = lactose_free is None or product["lactose_free"] == lactose_free
        vegan_flag = vegan is None or product["vegan"] == vegan
        if (
            gluten_flag
            and lactose_flag
            and vegan_flag
        ):
            answer.append(product["name"])
    return "Not found" if not answer else ", ".join(answer)


@tool(parse_docstring=True)
def food_check(product_name: str) -> str:
    """
    Check the gluten and lactose free and vegan status of a product.

    Args:
        product_name (str): The name of the product to check.

    Returns:
        str: A string containing the gluten and lactose free and vegan status of the product.
    """
    known_products = []
    for product in PRODUCTS.values():
        known_products.append(product["name"])
        if product["name"].strip().lower() == product_name.strip().lower():
            return (
                f"{product_name}:"
                f" gluten-free: {product['gluten_free']}"
                f" lactose-free: {product['lactose_free']}"
                f" vegan: {product['vegan']}"
            )
    return f"Unknown product {product_name}, Known Products: {', '.join(known_products)}"


@tool(parse_docstring=True)
def food_rnd_basket(n: int) -> str:
    """Return n random products.

    Args:
        n: How many products to return.
    """
    answer = []
    for i in range(n):
        rnd = random.randint(1, len(PRODUCTS))
        product = PRODUCTS[str(rnd)]
        answer.append(product["name"])
    return ', '.join(answer)

TOOLS = [food_search, food_check, food_rnd_basket]


def print_schemas():
    """Print each tool's schema exactly as the model receives it."""
    for t in TOOLS:
        print(json.dumps(convert_to_openai_tool(t), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    print_schemas()
