import os
import ast
import re
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")

client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=NVIDIA_API_KEY,
)


def call_nvidia_llm(messages):
    completion = client.chat.completions.create(
        model="meta/llama-3.1-70b-instruct",
        messages=messages,
        temperature=0.2,
        top_p=0.9,
        max_tokens=4096,
        stream=False,  # IMPORTANT
    )

    return completion.choices[0].message.content


GROQ_API_KEY = os.getenv("GROQ_API_KEY")

groq_client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=GROQ_API_KEY,
)


def call_groq_llm(messages):
    completion = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages,
        temperature=0.2,
        top_p=0.9,
        max_tokens=4096,
        stream=False,
    )

    return completion.choices[0].message.content


def generate_patch_from_llm(messages):
    try:
        print("Using NVIDIA LLM...")
        return call_nvidia_llm(messages)
    except Exception as e:
        print("NVIDIA failed. Switching to Groq fallback...")
        return call_groq_llm(messages)


def validate_llm_patch(content: str) -> bool:
    """
    Strict validation to ensure LLM returned only raw Python code.
    """
    if "```" in content:
        return False

    explanation_patterns = [
        r"here is",
        r"fixed code",
        r"updated code",
        r"explanation",
        r"this fixes",
        r"the issue",
    ]

    lower_content = content.lower()
    for pattern in explanation_patterns:
        if re.search(pattern, lower_content):
            return False

    try:
        ast.parse(content)
    except SyntaxError:
        return False

    return True
