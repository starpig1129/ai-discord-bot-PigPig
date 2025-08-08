# Eat System - Machine Learning Model

**File:** [`cogs/eat/train/train.py`](cogs/eat/train/train.py)

The `Train` class encapsulates the machine learning component of the "Eat What" system. It is responsible for training a personalized recommendation model for each server and using that model to predict food preferences.

## `Train` Class

### `__init__(self, db: DB, ...)`

Initializes the training manager.

*   **Parameters:**
    *   `db` (DB): An instance of the database class, used to fetch training data.
    *   Other parameters control the model's architecture and training hyperparameters (embedding dimensions, hidden layers, learning rate, etc.).

### `genModel(self, discord_id: str)`

This is the core training method. It builds and trains a recommendation model based on a server's historical data.

*   **Parameters:**
    *   `discord_id` (str): The ID of the server for which to train the model.
*   **Process:**
    1.  **Data Loading:** It uses a `DataLoader` to fetch all search records for the given `discord_id` from the database.
    2.  **Data Processing:** It processes the raw data, extracting features like restaurant titles, tags, and user-provided keywords.
    3.  **Vocabulary Creation:** It builds a vocabulary of all unique words from the processed data.
    4.  **Tensor Conversion:** The data is converted into numerical tensors that the model can understand.
    5.  **Model Training:** It initializes a `Net` model (a neural network defined in `cogs/eat/train/model.py`) and trains it on the tensor data for a set number of epochs. The user's ratings (`self_rate` from the database) implicitly influence the training data distribution.
    6.  **Saving:** After training, the model's state (`.model` file) and the vocabulary mapping (`.pickle` file) are saved to the `models/` directory, named after the `discord_id`.

### `predict(self, discord_id: str)`

Uses a pre-trained model to generate a food recommendation.

*   **Parameters:**
    *   `discord_id` (str): The ID of the server to generate a prediction for.
*   **Process:**
    1.  It loads the saved model and vocabulary files for the specified `discord_id`.
    2.  It feeds a random seed from the server's vocabulary into the model.
    3.  The model outputs a probability distribution over the entire vocabulary.
    4.  It uses this distribution to randomly select and return a predicted keyword.
*   **Returns:** A string containing the predicted food keyword (e.g., "ramen"). Returns `None` if no model exists for the server.