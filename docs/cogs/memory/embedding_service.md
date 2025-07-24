# Memory System - Embedding Service

**File:** [`cogs/memory/embedding_service.py`](cogs/memory/embedding_service.py)

The `EmbeddingService` is a critical component responsible for converting natural language text into high-dimensional numerical vectors, known as embeddings. These embeddings capture the semantic meaning of the text, enabling the system to perform similarity searches.

## `EmbeddingService` Class

### `__init__(self, profile: MemoryProfile)`

Initializes the embedding service based on a given memory profile.

*   **Parameters:**
    *   `profile` (MemoryProfile): A data class containing configuration for the memory system, including the `embedding_model` name, `embedding_dimension`, and hardware preferences (`cpu_only`).
*   **Process:**
    1.  **Device Detection:** It calls `_detect_device()` to automatically select the best available hardware (`cuda`, `mps`, or `cpu`).
    2.  **Model Identification:** It determines the type of model (e.g., `Qwen3-Embedding` or a standard `SentenceTransformer`) to use the correct loading and encoding logic.
    3.  **Fallback Setup:** It defines a fallback model to use if the primary model fails to load.

### Key Methods

#### `get_model(self)`

A lazy-loading method that retrieves the embedding model. If the model hasn't been loaded yet, it calls `_load_model` to initialize it. This ensures that the model is only loaded into memory when it's first needed.

#### `_load_model(self)`

Handles the complex logic of loading the model from the Hugging Face Hub.
*   It first attempts to load the primary model specified in the configuration.
*   It includes specific logic for different model types, such as `_load_qwen3_model` for Qwen models.
*   If the primary model fails to load, it automatically attempts to load a reliable fallback model (`paraphrase-multilingual-MiniLM-L12-v2`).
*   After loading, it performs a test encoding to verify that the model's actual output dimension matches the configured dimension, adjusting the configuration if necessary.

#### `encode_batch(self, texts: List[str], ...)`

The main method for converting a list of texts into a batch of embeddings.

*   **Parameters:**
    *   `texts` (List[str]): A list of text strings to be encoded.
*   **Process:**
    1.  It retrieves the model using `get_model()`.
    2.  It preprocesses the texts (e.g., cleaning whitespace).
    3.  It calls the appropriate encoding method based on the model type (`_encode_qwen3_batch` or `_encode_sentence_transformers_batch`).
    4.  The model processes the texts in batches to optimize performance and manage memory usage.
    5.  It returns the embeddings as a NumPy array.
*   **Returns:** A NumPy array of shape `(num_texts, embedding_dimension)`.

## `EmbeddingServiceManager` Class

This is a singleton manager that ensures only one instance of each embedding model is loaded into memory, even if multiple components request it. It maintains a cache of `EmbeddingService` instances keyed by their model name.