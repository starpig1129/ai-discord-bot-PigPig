# Summarizer Cog Documentation

## Overview

The Summarizer cog provides AI-powered conversation summarization using LangChain agents. It allows users to summarize recent chat history in a Discord channel, extracting key themes, decisions, and action items while maintaining links back to the original messages.

## Features

- **AI-Powered Summarization**: Uses advanced language models (via LangChain) to synthesize conversation history.
- **Source Mapping**: Automatically maps AI-generated references back to original Discord messages with clickable links.
- **Configurable Scope**: Users can specify how many messages to analyze.
- **Custom Personas**: Support for custom AI personas (e.g., "Professional Meeting Recorder", "Witty Critic").
- **Robust Text Splitting**: Automatically handles long summaries by splitting them into multiple Discord embeds.
- **Dual Limits**: Enforces both message count and character count limits to prevent token overflow.

## Commands

### `/summarize`
Summarizes the conversation history of the current channel.

**Parameters**:
- `limit` (int, optional, default: 100): The maximum number of messages to search back in history.
- `persona` (string, optional): Set the AI's summary persona (e.g., "A professional meeting recorder").
- `only_me` (boolean, optional, default: False): If True, the summary will only be visible to you (ephemeral message).

**Behavior**:
1. Fetches channel history up to the specified `limit`.
2. Filters out non-text messages and prioritizes human messages for analysis.
3. Formats messages with unique IDs (`[MSG-1]`, `[MSG-2]`, etc.) and timestamps.
4. Calls the AI model with a specialized system prompt.
5. Post-processes the AI output to replace `[MSG-ID]` tags with clickable `[[Source]]` links.
6. Sends the summary as one or more rich embeds.

## Technical Implementation

### Class Structure
```python
class SummarizerCog(commands.Cog):
    def __init__(self, bot):
        self.MAX_CHAR_COUNT = 15000  # Character limit for input context
        self.EMBED_DESC_LIMIT = 4000  # Character limit for individual embed descriptions
```

### Process Flow

#### 1. Message Collection
The cog iterates through the channel history in reverse chronological order. It collects human messages until either the `limit` is reached or the `MAX_CHAR_COUNT` (15,000 characters) is exceeded. Bot messages are included as context but marked differently.

#### 2. Prompt Engineering
The system prompt instructs the AI to:
- Identify core themes, questions, and decisions.
- Extract action items.
- Ignore small talk.
- Use a bulleted list format.
- **Crucial**: Attach the source `[MSG-ID]` to every summary point.

#### 3. AI Invocation
Uses `langchain.agents.create_agent` with the `init_chat_model`. It includes a `ModelCallLimitMiddleware` to ensure exactly one model call per request, preventing runaway agent loops.

#### 4. Post-Processing & Linking
The raw AI response is processed using regex to find `[MSG-ID]` patterns. These are cross-referenced with a `source_mapping` dictionary containing the `jump_url` of the original Discord messages, resulting in clickable links in the final embed.

#### 5. Output Management
If the generated summary exceeds Discord's embed description limit (4096 characters), `_split_text_robustly` divides the content into logical chunks and sends them as sequential embeds.

## Dependencies

- `discord.py`: Discord API interaction
- `langchain`: AI agent and message management
- `langchain_core`: HumanMessage and AIMessage schemas
- `ModelManager`: Centralized LLM configuration
- `func.report_error`: Standardized error reporting

## Usage Examples

### Basic Summary
```
/summarize limit:50
```
*Summarizes the last 50 messages using the default professional persona.*

### Professional Persona
```
/summarize limit:100 persona:"A strict military officer" only_me:True
```
*Summarizes the last 100 messages with a military tone, visible only to the user.*

## Related Files

- `cogs/summarizer.py`: Main implementation
- `llm/model_manager.py`: Model selection and fallback logic
- `function/func.py`: Utility functions and error reporting