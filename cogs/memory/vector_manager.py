import importlib
from typing import Type, Optional, TYPE_CHECKING

from discord.ext.commands import Bot
from langchain_core.embeddings import Embeddings

from addons.settings import MemoryConfig
from .vector_store_interface import VectorStoreInterface

if TYPE_CHECKING:
    from bot import PigPig as Bot

class VectorManager:
    """
    Factory class to dynamically initialize and provide a vector store instance based on settings.
    """

    def __init__(self, bot: "Bot", settings: "MemoryConfig"):
        """
        Initializes the VectorManager.

        Args:
            bot (Bot): The discord bot instance.
            settings (Settings): The application settings.
        """
        self.bot = bot
        self.settings = settings
        # The embedding model will be set later from the ModelManager.
        self.embedding_model: Optional[Embeddings] = None
        self._store: VectorStoreInterface = self._initialize_store()

    def _get_store_class(self, store_type: str) -> Type[VectorStoreInterface]:
        """
        Dynamically imports and returns the vector store class from the 'vector_stores' directory.

        Args:
            store_type (str): The type of the vector store (e.g., "qdrant").

        Returns:
            Type[VectorStoreInterface]: The vector store class.

        Raises:
            ValueError: If the store class cannot be found or imported.
        """
        try:
            # Construct the module path relative to the current package.
            module_name = f".vector_stores.{store_type}_store"
            # Convert snake_case to CamelCase for the class name (e.g., qdrant -> QdrantStore).
            class_name = "".join(word.capitalize() for word in store_type.split('_')) + "Store"
            # Perform the dynamic import.
            module = importlib.import_module(module_name, package="cogs.memory")
            return getattr(module, class_name)
        except (ImportError, AttributeError) as e:
            raise ValueError(f"Could not find or import vector store for type '{store_type}'. Error: {e}")

    def _initialize_store(self) -> VectorStoreInterface:
        """
        Initializes the vector store based on the settings.

        Returns:
            VectorStoreInterface: An instance of the configured vector store.
        """
        store_type = self.settings.vector_store_type
        store_class = self._get_store_class(store_type)
        # Dependency injection: Pass settings and the (currently None) embedding model.
        return store_class(settings=self.settings, embedding_model=self.embedding_model)

    @property
    def store(self) -> VectorStoreInterface:
        """Provides public access to the vector store instance."""
        return self._store

    async def initialize(self):
        """
        Performs asynchronous initialization for the vector store.
        """
        await self.store.ensure_storage()