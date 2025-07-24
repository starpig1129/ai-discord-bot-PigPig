# Memory System - Configuration

**File:** [`cogs/memory/config.py`](cogs/memory/config.py)

This module is responsible for managing all configurations for the memory system. It features a hardware detection system that automatically selects an appropriate performance profile, ensuring the system runs optimally on different machines.

## `MemoryConfig` Class

This is the main class for loading and accessing configuration settings from `settings.json`.

### `get_current_profile(self) -> MemoryProfile`

This is the most important method in the class. It determines which performance profile to use.

*   **Automatic Detection (Default):** If `auto_detection` is enabled in the configuration, it uses the `HardwareDetector` to assess the system's hardware and selects the most powerful compatible profile from a predefined list.
*   **Manual Selection:** If `auto_detection` is disabled, it uses the profile name specified in the configuration file.

## `HardwareDetector` Class

This class automatically detects the host system's hardware specifications.

### `detect_hardware(self) -> HardwareSpec`

Detects the system's RAM, CPU cores, and GPU availability and memory. It uses `psutil` for RAM/CPU detection and `nvidia-smi` (for NVIDIA) or `rocm-smi` (for AMD) command-line tools to detect GPU properties.

### `recommend_profile(self, profiles: Dict[str, MemoryProfile]) -> str`

Compares the detected hardware against a list of available `MemoryProfile` objects and returns the name of the best-fitting profile. It prioritizes more powerful profiles if the hardware is compatible.

## `MemoryProfile` Data Class

This data class defines a specific set of performance and operational parameters for the memory system. The system includes several predefined profiles, such as:

*   **`qwen3_high_performance`:** Requires a GPU and significant RAM, uses a large, high-quality embedding model.
*   **`high_performance`:** Requires a GPU and RAM, uses a standard embedding model.
*   **`medium_performance`:** Can run with or without a GPU, uses a smaller, efficient embedding model.
*   **`low_performance`:** Designed for low-resource systems, runs on CPU only, and disables vector search capabilities entirely.

Each profile specifies key parameters like:
*   `min_ram_gb`: The minimum required system RAM.
*   `gpu_required`: Whether a GPU is mandatory.
*   `vector_enabled`: Whether to enable semantic search.
*   `embedding_model`: The name of the Hugging Face model to use for embeddings.
*   `embedding_dimension`: The dimension of the vectors produced by the model.
*   `batch_size`: The number of items to process at once during embedding.