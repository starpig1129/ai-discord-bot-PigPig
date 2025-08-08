# Memory System - Reranker Service

**File:** [`cogs/memory/reranker_service.py`](cogs/memory/reranker_service.py)

The `RerankerService` is an optional but powerful component that significantly improves the relevance of search results. It uses a specialized cross-encoder model to perform a more computationally intensive but accurate scoring of candidate messages against the user's query.

## `RerankerService` Class

### `__init__(self, profile: MemoryProfile, ...)`

Initializes the reranker service.

*   **Parameters:**
    *   `profile` (MemoryProfile): The current memory profile, used for hardware settings.
    *   `reranker_model` (str): The name of the Hugging Face model to use (e.g., `Qwen/Qwen3-Reranker-0.6B`).

### `rerank_results(self, query, candidates, ...)`

This is the main public method of the class. It takes a query and a list of candidate messages (typically the initial results from a semantic search) and returns a re-ordered list based on a more accurate relevance score.

*   **Parameters:**
    *   `query` (str): The user's search query.
    *   `candidates` (List[Dict]): A list of message dictionaries.
    *   `score_field` (str): The key in the message dictionary that contains the text to be scored (e.g., "content").
    *   `top_k` (Optional[int]): The number of top results to return.
*   **Returns:** A new list of message dictionaries, sorted by the `rerank_score`, which has been added to each dictionary.

## Core Logic

### Cross-Encoder Model

Unlike the `EmbeddingService`, which uses a bi-encoder to create separate vectors for the query and the documents, the `RerankerService` uses a **cross-encoder**. This means it feeds both the query and a candidate document into the model *at the same time*. This allows the model to perform a much deeper, attention-based comparison between the two texts, resulting in a more accurate relevance score. The trade-off is that this process is much slower and cannot be pre-calculated and stored in a vector index.

### `_compute_rerank_scores(...)`

This method implements the scoring logic based on the official examples for the Qwen3-Reranker model.

1.  **Formatting:** For each candidate document, it creates a formatted string that includes the query and the document text, wrapped in a specific prompt structure.
2.  **Tokenization:** It tokenizes these formatted pairs.
3.  **Inference:** It feeds the tokenized pairs into the reranker model in small batches.
4.  **Score Extraction:** The model's output (logits) for the "yes" and "no" tokens are extracted.
5.  **Probability Calculation:** A `log_softmax` is applied to these logits, and the final probability for the "yes" token is calculated. This probability becomes the `rerank_score`.

This process is repeated for all candidate documents, and the final list is sorted by this new score.