# File: `llm/utils/model_init.py`

## Overview
Shared model instantiation helper with vLLM support via the OpenAI-compatible API.

## Classes

No classes defined in this file.

## Functions

### `create_model_instance(model_name) -> BaseChatModel`
Create a LangChain chat model, routing 'vllm:' prefixed names through ChatOpenAI.
