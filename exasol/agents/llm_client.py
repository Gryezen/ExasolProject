"""
agents/llm_client.py — one shared wrapper around the Gemini API's forced
function calling, used by every agent that needs structured (never
free-text) model output: extraction, reasoning, action, relationships,
and chat's SQL generation.

Originally this project called the Anthropic API directly from each agent
using forced tool_choice (the model is not allowed to answer in prose; it
must call the one tool it's given, so the response is always parseable).
Gemini's equivalent is FunctionCallingConfigMode.ANY with a single
FunctionDeclaration. This module centralizes that mapping so each agent
file keeps the same shape it had before — build a JSON-schema tool,
call one function, get back a plain dict — without five copies of
Gemini-specific plumbing.

Tool schemas are written in the same style used throughout this project
before the switch (a plain JSON-schema dict: {"type": "object",
"properties": {...}, "required": [...]}.). google-genai's
FunctionDeclaration accepts that directly via parameters_json_schema, so
no schema rewriting is needed at call sites.
"""

from google import genai
from google.genai import types


class LLMCallError(Exception):
    """Raised when the model doesn't return the forced function call at
    all (e.g. safety block, empty candidates). Mirrors the old
    'model did not return a tool_use block' failure mode so callers don't
    need to change their error handling.
    """


def call_tool(
    api_key: str,
    model: str,
    system_prompt: str,
    tool_name: str,
    tool_description: str,
    tool_schema: dict,
    user_content: str,
    max_output_tokens: int = 4096,
) -> dict:
    """Force the model to call exactly one named tool and return its
    arguments as a plain dict.

    Equivalent to the old pattern:
        client = anthropic.Anthropic(api_key=...)
        response = client.messages.create(..., tool_choice={"type": "tool", "name": tool_name})
        tool_use_block = next(b for b in response.content if b.type == "tool_use")
        return tool_use_block.input
    """
    client = genai.Client(api_key=api_key)

    function_declaration = types.FunctionDeclaration(
        name=tool_name,
        description=tool_description,
        parameters_json_schema=tool_schema,
    )

    response = client.models.generate_content(
        model=model,
        contents=user_content,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            max_output_tokens=max_output_tokens,
            tools=[types.Tool(function_declarations=[function_declaration])],
            tool_config=types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(
                    mode=types.FunctionCallingConfigMode.ANY,
                    allowed_function_names=[tool_name],
                )
            ),
        ),
    )

    candidates = response.candidates or []
    for candidate in candidates:
        parts = candidate.content.parts if candidate.content else []
        for part in parts:
            if part.function_call is not None and part.function_call.name == tool_name:
                # function_call.args is already a plain dict (google-genai
                # decodes the protobuf Struct for you).
                return dict(part.function_call.args)

    raise LLMCallError(f"Model did not return a call to '{tool_name}'")
