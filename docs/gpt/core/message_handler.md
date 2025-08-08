# GPT Core - Message Handler

**File:** [`gpt/core/message_handler.py`](gpt/core/message_handler.py)

The `MessageHandler` is the highest-level component in the AI response pipeline. It acts as the primary entry point for all incoming Discord messages and orchestrates the entire process of generating a response.

## `MessageHandler` Class

### `__init__(self, bot, action_dispatcher, performance_monitor)`

Initializes the handler with its key dependencies.

*   **Dependencies:**
    *   `bot`: The main bot instance, used to access cogs and other bot-wide resources.
    *   `ActionDispatcher`: The decision-making component that the handler will delegate tasks to.
    *   `PerformanceMonitor`: Used to track metrics for the response generation process.

### `async handle_message(self, message: discord.Message)`

This is the main method of the class and the entry point for the entire AI response pipeline. It is called directly from the `on_message` event in the main `bot.py` file.

*   **Parameters:**
    *   `message` (discord.Message): The Discord message object to be processed.
*   **Process:**
    1.  **Performance Tracking:** It starts a timer on the `PerformanceMonitor` to measure the total response time.
    2.  **Cache Check:** It first checks the `processing_cache` to see if an identical request has been processed recently. If a cached response is found, it is sent immediately, and the process ends.
    3.  **Permission & Mode Check:** It calls the `ChannelManager` cog to verify that the bot is allowed to respond in the current channel and to check for any special channel modes.
    4.  **Story Mode Routing:** If the channel is in "story mode," it bypasses the standard pipeline and routes the message directly to the `StoryManagerCog` for processing.
    5.  **Standard Pipeline Invocation:** If the message is a standard query (e.g., the bot is mentioned), it proceeds with the main pipeline:
        *   It sends an initial "Thinking..." message to the channel.
        *   It calls `self.action_dispatcher.choose_act(...)`, which performs the context gathering and action selection, returning an `execute_action` function.
        *   It then `await`s this `execute_action` function, which triggers the tool execution and final LLM response generation.
    6.  **Error Handling:** The entire process is wrapped in a `try...except` block to catch any errors that occur during the pipeline and send a user-friendly error message back to the channel.
    7.  **Performance Tracking:** Finally, it stops the `total_response_time` timer on the `PerformanceMonitor`.