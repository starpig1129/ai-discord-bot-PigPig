# Model Management Cog

**File:** [`cogs/model_management.py`](cogs/model_management.py)

This cog is a specialized tool for the bot owner to manage the locally hosted AI model. It provides commands to load and unload the model from memory, which is particularly useful for managing GPU resources without needing to restart the entire bot.

## Features

*   **Resource Management:** Allows for dynamic loading and unloading of the local AI model, freeing up significant GPU memory when the model is not needed.
*   **Developer-only Access:** All commands are strictly restricted to the `BOT_OWNER_ID` defined in the `.env` file.
*   **State Synchronization:** It interacts with the core response generator (`gpt.core.response_generator`) to ensure the rest of the bot is aware of the model's current state (loaded or unloaded).

## Main Command

### `/model_management`

The sole command for managing the AI model.

*   **Parameters:**
    *   `action` (Choice): The action to perform.
        *   `卸載模型 (Unload Model)`: Removes the model and tokenizer from memory, clears the CUDA cache, and runs the garbage collector.
        *   `載入模型 (Load Model)`: Loads the model specified by the `MODEL_NAME` environment variable into memory.
*   **Permissions:** Bot Owner Only

## Core Logic

### `execute_model_operation(self, action: str, ...)`

This function contains the logic for the two main actions:

*   **Unloading:** It retrieves the current model and tokenizer instances using `get_model_and_tokenizer()`, sets them to `None`, deletes the objects, and then triggers Python's garbage collection and `torch.cuda.empty_cache()` to ensure memory is released.
*   **Loading:** It calls the `reload_model()` method.

### `reload_model(self)`

This method handles the process of loading the model from Hugging Face. It uses the `AutoTokenizer` and `AutoModel` classes from the `transformers` library to download and initialize the model specified in the `.env` file. After loading, it calls `set_model_and_tokenizer()` to make the new instances globally available to the bot.