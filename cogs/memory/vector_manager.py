import importlib
import logging
import inspect
from typing import Type, Optional, TYPE_CHECKING, Callable, Awaitable, Dict

from discord.ext.commands import Bot
from langchain_core.embeddings import Embeddings

from addons.settings import MemoryConfig
from .vector_store_interface import VectorStoreInterface
from function import func

if TYPE_CHECKING:
    from bot import PigPig as Bot

logger = logging.getLogger(__name__)

# Type of a provider factory: can be sync (return Embeddings) or async (return Awaitable[Embeddings])
EmbedFactory = Callable[[MemoryConfig], "Embeddings"]
AsyncEmbedFactory = Callable[[MemoryConfig], Awaitable["Embeddings"]]

# Global registry for embedding providers; other modules can register via register_embedding_provider
_embedding_providers: Dict[str, Callable[..., object]] = {}


def register_embedding_provider(name: str):
    """
    Decorator to register an embedding provider factory under a canonical name.

    Example:
        @register_embedding_provider("openai")
        def openai_factory(settings: MemoryConfig) -> Embeddings:
            ...
    """
    def decorator(factory: Callable[[MemoryConfig], object]):
        _embedding_providers[name] = factory
        logger.info("Registered embedding provider: %s", name)
        return factory
    return decorator


class VectorManager:
    """
    Factory class to dynamically initialize and provide a vector store instance and embedding model.

    Responsibilities:
    - Manage an embedding provider registry (pluggable).
    - Initialize embedding model asynchronously based on settings.
    - Initialize vector store with dependency injection of the embedding model.
    """

    def __init__(self, bot: "Bot", settings: "MemoryConfig"):
        """
        Args:
            bot: The discord bot instance.
            settings: The application settings (should contain vector_store_type and embedding provider name).
        """
        self.bot = bot
        self.settings = settings
        self.embedding_model: Optional[Embeddings] = None
        self._store: Optional[VectorStoreInterface] = None
        # store is intentionally left uninitialized until async initialize is called
        logger.debug("VectorManager created with settings: %s", getattr(settings, "vector_store_type", None))

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
            module_name = f".vector_stores.{store_type}_store"
            class_name = "".join(word.capitalize() for word in store_type.split('_')) + "Store"
            module = importlib.import_module(module_name, package="cogs.memory")
            return getattr(module, class_name)
        except (ImportError, AttributeError) as e:
            msg = f"Could not find or import vector store for type '{store_type}'. Error: {e}"
            logger.exception(msg)
            raise ValueError(msg)

    def _initialize_store(self) -> VectorStoreInterface:
        """
        Creates the configured VectorStore instance, injecting the embedding model.
        """
        if not hasattr(self.settings, "vector_store_type"):
            raise ValueError("settings must provide vector_store_type")
        store_type = self.settings.vector_store_type
        store_class = self._get_store_class(store_type)
        return store_class(settings=self.settings, embedding_model=self.embedding_model)

    async def _initialize_embedding(self) -> Embeddings:
        """
        Initializes embedding model according to settings.embedding_provider.

        This method looks up a provider in the registry and calls it with the MemoryConfig.
        The provider can be synchronous or asynchronous.

        Raises:
            ValueError: if provider not configured or provider not registered.
        """
        provider_name = getattr(self.settings, "embedding_provider", None)
        if not provider_name:
            err = ValueError("embedding_provider setting is required")
            try:
                await func.report_error(err, "Embedding provider not configured")
            except Exception:
                logger.exception("Failed to report missing embedding provider")
            raise err

        factory = _embedding_providers.get(provider_name)
        if factory is None:
            err = ValueError(f"No embedding provider registered under name '{provider_name}'")
            try:
                await func.report_error(err, f"Missing embedding provider registration: {provider_name}")
            except Exception:
                logger.exception("Failed to report missing embedding provider registration")
            raise err

        try:
            result = factory(self.settings)
            # support async factories
            if inspect.isawaitable(result):
                embeddings = await result  # type: ignore
            else:
                embeddings = result  # type: ignore
            if not isinstance(embeddings, Embeddings):
                raise TypeError("Embedding provider did not return an Embeddings instance")
            return embeddings
        except Exception as e:
            logger.exception("Failed to initialize embedding provider %s: %s", provider_name, e)
            await func.report_error(e, f"Failed to initialize embedding provider {provider_name}")
            raise

    async def initialize(self):
        """
        Async initialization entrypoint.

        1) Initialize embedding model
        2) Initialize vector store with the embedding model injected
        3) Call store.ensure_storage()
        """
        try:
            self.embedding_model = await self._initialize_embedding()
            # initialize store now that embedding_model exists
            self._store = self._initialize_store()
            await self._store.ensure_storage()
            logger.info("VectorManager initialization complete")
        except Exception as e:
            logger.exception("VectorManager failed to initialize: %s", e)
            await func.report_error(e, "VectorManager initialization failed")
            raise

    @property
    def store(self) -> VectorStoreInterface:
        """Provides public access to the vector store instance."""
        if self._store is None:
            raise RuntimeError("VectorManager.store accessed before initialize()")
        return self._store

    def get_embedding_model(self) -> Embeddings:
        """Return initialized embedding model synchronously (after initialize)."""
        if self.embedding_model is None:
            raise RuntimeError("Embedding model accessed before initialize()")
        return self.embedding_model

    # Helper for tests or advanced usage to set embedding model directly
    def set_embedding_model_for_tests(self, model: Embeddings):
        self.embedding_model = model
        # if store already exists, re-initialize it to inject the new embedding
        if self._store is not None:
            self._store = self._initialize_store()