import yaml
import asyncio
import logging
import os
import sys
import uuid
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

def _load_yaml_file(path: str) -> dict:
    """安全讀取 YAML 檔案，失敗時使用 func.report_error 回報並回傳空 dict"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data
    except Exception as e:
        try:
            from function import func
            asyncio.create_task(func.report_error(e, "addons/settings.py/_load_yaml_file"))
        except Exception:
            logger.error(f"Failed to load YAML file ({path}): {e}")
        return {}

def _get_config_root() -> str:
    """Read CONFIG_ROOT environment variable.

    If CONFIG_ROOT is not set, report the issue via func.report_error and
    fall back to 'config' to allow startup to continue.
    """
    try:
        root = os.getenv("CONFIG_ROOT")
        if root is None:
            raise KeyError("CONFIG_ROOT environment variable not set")
        # Remove any trailing slashes for consistent joins
        return root.rstrip("/\\")
    except KeyError:
        try:
            from function import func
            asyncio.create_task(
                func.report_error(Exception("CONFIG_ROOT environment variable not set"), "addons/settings.py/_get_config_root")
            )
        except Exception:
            logging.getLogger(__name__).warning("CONFIG_ROOT environment variable not set; defaulting to './base_configs'")
        return "./base_configs"

# Evaluate CONFIG_ROOT at module import time so the module-level config loaders
# below use the configured root directory.
CONFIG_ROOT = _get_config_root()
logger = logging.getLogger(__name__)
logger.debug(f"addons.settings CONFIG_ROOT={CONFIG_ROOT}")


class BaseConfig:
    """對應 config/base.yaml 的設定物件"""

    def __init__(self, path: str = "config/base.yaml") -> None:
        self.path = path
        data = _load_yaml_file(path)
        self.prefix: str = data.get("prefix", "/")
        self.activity: list = data.get("activity", [])
        self.ipc_server: dict = data.get("ipc_server", {})
        self.version: str = data.get("version", "")
        self.logging: dict = data.get("logging", {})
        # Color configuration for logging
        self.enable_colored_logs: bool = data.get("enable_colored_logs", True)
        self.colored_logs_config: dict = data.get("colored_logs_config", {})


class LLMConfig:
    """對應 config/llm.yaml 的設定物件"""

    def __init__(self, path: str = "config/llm.yaml") -> None:
        self.path = path
        self.data: dict = _load_yaml_file(path)
        self.model_priorities: list = self.data.get("model_priorities", [])
        self.google_search_agent: str = self.data.get("google_search_agent", "gemini-2.0-flash")


class UpdateConfig:
    """對應 config/update.yaml 的設定物件"""

    def __init__(self, path: str = "config/update.yaml") -> None:
        self.path = path
        data = _load_yaml_file(path)
        self.auto_update: dict = data.get("auto_update", {})
        self.security: dict = data.get("security", {})
        self.notification: dict = data.get("notification", {})
        self.restart: dict = data.get("restart", {})
        self.github: dict = data.get("github", {})

class MusicConfig:
    """對應 config/music.yaml 的設定物件"""

    def __init__(self, path: str = "config/music.yaml") -> None:
        self.path = path
        data = _load_yaml_file(path)
        self.music_temp_base: dict = data.get("music_temp_base", "temp/music")
        self.ffmpeg : dict = data.get("ffmpeg", {})
        self.youtube_cookies_path: str = data.get("youtube_cookies_path", "./data/youtube_cookies.txt")

class PromptConfig:
    """對應 config/prompt/*.yaml 的設定物件"""

    def __init__(self, path: str = "config/prompt") -> None:
        self.path = path
    
    def get_system_prompt(self, agent_name: str, bot_id: int | None = None, message=None) -> str:
        """
        從指定的 agent 設定中取得 system_prompt，並嘗試套用已知變數替換
        
        Args:
            agent_name: agent 名稱
            bot_id: 可選的機器人 ID（用於替換 {bot_id}）
            message: 可選的 Discord 訊息物件（未使用，但保留以備將來擴充）
        
        Returns:
            system_prompt 字串，若找不到則返回空字串
        """
        try:
            from llm.prompting.manager import get_prompt_manager

            logger = logging.getLogger(__name__)
            config_file = f"{self.path}/{agent_name}.yaml"
            logger.debug(f"PromptConfig.get_system_prompt: loading config_file={config_file}")

            prompt_manager = get_prompt_manager(config_file)
            # 嘗試記錄 prompt_manager 的 config_path（若有）
            try:
                pm_config_path = getattr(prompt_manager, "config_path", None)
                logger.debug(f"PromptConfig: prompt_manager.config_path={pm_config_path}")
            except Exception:
                logger.debug("PromptConfig: prompt_manager has no attribute 'config_path'")

            # 取得原始 prompt（尚未套用動態變數）
            system_prompt = prompt_manager.compose_prompt(None)
            logger.debug(f"PromptConfig.get_system_prompt: raw system_prompt={system_prompt!r}")

            # 準備可替換變數（盡可能填入已知值）
            try:
                from addons.tokens import tokens
                bot_owner_id = getattr(tokens, "bot_owner_id", 0)
            except Exception:
                bot_owner_id = 0

            try:
                # 優先從 prompt_manager 的 loader 讀取 base 配置
                config = prompt_manager.loader.load_yaml_config()
                base_cfg = config.get("base", {})
                bot_name = base_cfg.get("bot_name", "🐖🐖")
                creator = base_cfg.get("creator", "星豬")
                environment = base_cfg.get("environment", "Discord server")
            except Exception:
                bot_name = "🐖🐖"
                creator = "星豬"
                environment = "Discord server"

            # 將 bot_id 明確轉為字串以供 format 使用
            bot_id_str = str(bot_id) if bot_id is not None else "{bot_id}"

            variables = {
                "bot_id": bot_id_str,
                "bot_owner_id": bot_owner_id,
                "bot_name": bot_name,
                "creator": creator,
                "environment": environment,
            }

            logger.debug(f"PromptConfig.get_system_prompt: variables={variables!r}")

            try:
                # 嘗試獲取語言管理器（可能在某些上下文中可用）
                lang_manager = None
                guild_id = None
                
                # 嘗試從全局變數或上下文獲取語言管理器
                try:
                    import discord
                    lang_manager = None  
                    guild_id = None     
                except Exception:
                    pass 
                
                formatted = prompt_manager.builder.format_with_variables(system_prompt, variables, lang_manager, guild_id)
                logger.debug(f"PromptConfig.get_system_prompt: formatted system_prompt={formatted!r}")
                return formatted if formatted else system_prompt if system_prompt else ''
            except Exception as e:
                logger.exception(f"Formatting system_prompt failed: {e}")
                return system_prompt if system_prompt else ''

        except Exception as e:
            # 先嘗試使用現有的報錯機制
            try:
                asyncio.create_task(func.report_error(e, f"loading {agent_name} system prompt"))
            except Exception:
                # 若報錯機制不可用，記錄本地日誌以便診斷
                logger = logging.getLogger(__name__)
                logger.exception(f"Error loading {agent_name} system prompt: {e}")
            return ''

class MemoryConfig:
    """Memory subsystem configuration object mapped from config/memory.yaml"""

    def __init__(self, path: str = "config/memory.yaml") -> None:
        self.path = path
        data = _load_yaml_file(path)

        # Toggle to enable/disable memory subsystem
        self.enabled: bool = bool(data.get("enabled", True))

        # Storage / vector store configuration
        self.procedural_data_path: str = data.get("procedural_data_path", "data/memory/procedural.db")
        self.episodic_data_path: str = data.get("episodic_data_path", "data/memory/episodic.db")
        self.vector_store_type: str = data.get("vector_store_type", "qdrant")
        self.qdrant_url: str = data.get("qdrant_url", "http://localhost:6333")
        self.qdrant_api_key: Optional[str] = data.get("qdrant_api_key", None)
        self.qdrant_collection_name: str = data.get("qdrant_collection_name", "ephemeral_memory")

        # Embedding provider selection and provider-specific settings.
        # provider values: base, openai, huggingface, ollama, google
        self.embedding_provider: str = data.get("embedding_provider", "google")
        # Embedding model defaults (generic)
        self.embedding_model_name: str = data.get("embedding_model_name", "gemini-embedding-001")
        self.embedding_dim: int = data.get("embedding_dim", 768)

        # Search tuning
        self.vector_search_k: int = data.get("vector_search_k", 5)
        self.keyword_search_k: int = data.get("keyword_search_k", 5)

        # Ollama provider options
        self.ollama_url: Optional[str] = data.get("ollama_url", "http://localhost:11434")
        # Generic provider options bag for future extensions
        self.provider_options: dict = data.get("provider_options", {})

        # Message threshold for triggering memory processing
        self.message_threshold: int = data.get("message_threshold", 100)

class LoggingConfig:
    """Comprehensive logging configuration management system.
    
    This class consolidates all logging configuration including:
    - Third-party library suppression rules
    - Logger initialization methods
    - Color configuration settings
    - Format templates
    - Root logger setup
    - System and guild-specific logging
    """
    
    def __init__(self):
        """Initialize LoggingConfig with comprehensive suppression rules and settings."""
        self.logger = logging.getLogger(__name__)
        
        # Third-party library suppression dictionary from main.py
        self.third_party_suppression = {
            # Database libraries - suppress completely to prevent standard format logs
            "sqlalchemy.engine.Engine": logging.CRITICAL,  # CRITICAL to completely suppress
            "sqlalchemy.engine.base": logging.CRITICAL,   # SQLAlchemy engine base
            "sqlalchemy.engine": logging.CRITICAL,        # SQLAlchemy engine general
            "sqlalchemy.pool": logging.CRITICAL,          # SQLAlchemy connection pool
            "sqlalchemy.pool.impl": logging.CRITICAL,     # SQLAlchemy pool implementations
            "sqlalchemy.dialects": logging.CRITICAL,      # SQLAlchemy dialects
            "sqlalchemy.dialects.sqlite": logging.CRITICAL, # SQLite dialect
            "sqlalchemy.dialects.mysql": logging.CRITICAL,  # MySQL dialect
            "sqlalchemy.dialects.postgresql": logging.CRITICAL, # PostgreSQL dialect
            "sqlalchemy.orm": logging.CRITICAL,           # SQLAlchemy ORM
            "sqlalchemy.orm.session": logging.CRITICAL,   # SQLAlchemy ORM session
            "sqlalchemy.orm.query": logging.CRITICAL,     # SQLAlchemy ORM query
            "sqlalchemy.orm.mapper": logging.CRITICAL,    # SQLAlchemy ORM mapper
            "sqlalchemy.sql": logging.CRITICAL,           # SQLAlchemy SQL compilation
            "sqlalchemy.util": logging.CRITICAL,          # SQLAlchemy utilities
            "sqlalchemy": logging.CRITICAL,               # Main SQLAlchemy logger
            "alembic": logging.CRITICAL,                  # Database migrations
            
            # HTTP libraries - suppress completely
            "httpx": logging.CRITICAL,  # CRITICAL to suppress HTTP request logs
            "httpx.client": logging.CRITICAL,
            "httpx._client": logging.CRITICAL,
            "urllib3.connectionpool": logging.CRITICAL,
            "urllib3.poolmanager": logging.CRITICAL,
            "urllib3": logging.CRITICAL,
            "urllib3.util": logging.CRITICAL,
            "requests": logging.CRITICAL,
            "requests.packages": logging.CRITICAL,
            "requests.models": logging.CRITICAL,
            "aiohttp": logging.CRITICAL,
            "aiohttp.client": logging.CRITICAL,
            "aiohttp.connector": logging.CRITICAL,
            
            # Web drivers - suppress completely
            "WDM": logging.CRITICAL,  # CRITICAL to suppress WebDriver manager logs
            "selenium": logging.CRITICAL,
            "selenium.webdriver": logging.CRITICAL,
            "selenium.common": logging.CRITICAL,
            "webdriver": logging.CRITICAL,
            "webdriver_manager": logging.CRITICAL,
            
            # System and utility libraries
            "jieba": logging.CRITICAL,
            "jieba.analyse": logging.CRITICAL,
            "jieba.posseg": logging.CRITICAL,
            "jieba.finalseg": logging.CRITICAL,
            "pkg_resources": logging.CRITICAL,  # Suppress deprecation warnings
            "setuptools": logging.CRITICAL,
            "pip._internal": logging.CRITICAL,
            "pip._internal.utils": logging.CRITICAL,
            
            # Discord and websockets - suppress verbose logs
            "discord": logging.WARNING,
            "discord.gateway": logging.WARNING,
            "discord.http": logging.WARNING,
            "discord.state": logging.WARNING,
            "discord.client": logging.WARNING,
            "discord.ext": logging.WARNING,
            "discord.ext.commands": logging.WARNING,
            "discord.ext.tasks": logging.CRITICAL,
            "discord.voice_client": logging.WARNING,
            "discord.message": logging.WARNING,
            "discord.user": logging.WARNING,
            "discord.guild": logging.WARNING,
            "websockets": logging.WARNING,
            "websockets.legacy": logging.WARNING,
            "websockets.protocol": logging.WARNING,
            "websockets.client": logging.WARNING,
        }
        
        # Additional suppression from bot.py
        self.additional_suppression = {
            # Server-specific libraries that might need suppression
            "cogs.memory": logging.WARNING,
            "asyncio": logging.WARNING,
            "uvloop": logging.WARNING,
        }
        
        # Combined suppression rules
        self._combined_suppression = {**self.third_party_suppression, **self.additional_suppression}
        
        # Additional database logger names for comprehensive suppression
        self.db_logger_names = [
            "sqlalchemy.engine.Engine",
            "sqlalchemy.engine.base.Engine",
            "sqlalchemy.engine.base.Connection",
            "sqlalchemy.engine.base.Executable",
            "sqlalchemy.engine.result",
            "sqlalchemy.engine.strategies",
            "sqlalchemy.pool.impl.QueuePool",
            "sqlalchemy.pool.impl.LifoQueueProxy",
            "sqlalchemy.pool.impl.StackedSharedProxy",
            "sqlalchemy.pool.events",
            "sqlalchemy.dialects.sqlite",
            "sqlalchemy.dialects.mysql",
            "sqlalchemy.dialects.postgresql",
            "sqlalchemy.orm.session",
            "sqlalchemy.orm.query",
            "sqlalchemy.orm.mapper",
            "sqlalchemy.orm.relationships",
            "sqlalchemy.orm.attributes",
            "sqlalchemy.orm.util",
            "sqlalchemy.sql.elements",
            "sqlalchemy.sql.selectable",
            "sqlalchemy.sql.dml",
            "sqlalchemy.sql.schema",
            "sqlalchemy.sql.types",
            "sqlalchemy.util.langhelpers",
            "sqlalchemy.util.concurrency",
        ]
        
        # Color configuration settings
        self.enable_colored_logs = getattr(base_config, 'enable_colored_logs', True)
        self.colored_logs_config = getattr(base_config, 'colored_logs_config', {})
        
        # Format templates
        self.log_format = (
            "[%(asctime)s] [%(levelname)s] [%(log_category)s] [%(custom_module)s] [%(function_name)s] "
            "[GUILD:%(guild_id)s] [USER:%(user_id)s] %(message)s"
        )
        
        self.enhanced_format = (
            "[%(asctime)s] [%(levelname)s] [%(log_category)s] [%(custom_module)s] [%(function_name)s] "
            "[GUILD:%(guild_id)s] [USER:%(user_id)s] [CID:%(correlation_id)s] "
            "%(message)s%(extra_context)s"
        )
        
        # Initialize color support
        self._init_color_support()
    
    def _init_color_support(self):
        """Initialize color support configuration."""
        # Color codes for different log levels
        self.level_colors = {
            'DEBUG': '\033[90m',      # Gray
            'INFO': '\033[92m',       # Green
            'WARNING': '\033[93m',    # Yellow
            'ERROR': '\033[91m',      # Red
            'CRITICAL': '\033[95m',   # Magenta/Dark Red
            'RESET': '\033[0m'        # Reset color
        }
        
        # Color codes for different modules
        self.module_colors = {
            'bot': '\033[94m',        # Blue
            'main': '\033[94m',
            'startup': '\033[94m',
            'cogs': '\033[96m',       # Cyan
            'utils': '\033[96m',
            'discord': '\033[95m',    # Magenta
            'sqlalchemy': '\033[95m',
            'httpx': '\033[95m',
            'web': '\033[93m',        # Orange/Yellow for web services
        }
    
    def suppress_third_party_logs(self):
        """Apply comprehensive third-party library suppression.
        
        This method suppresses all third-party library logs to prevent
        excessive logging noise while maintaining proper application logging levels.
        """
        # Apply suppression to ALL third-party loggers BEFORE setting up our handler
        for lib_name, lib_level in self._combined_suppression.items():
            lib_logger = logging.getLogger(lib_name)
            lib_logger.setLevel(lib_level)
            lib_logger.propagate = False  # Prevent propagation to root logger
            
            # Also suppress any child loggers
            for handler in lib_logger.handlers[:]:
                lib_logger.removeHandler(handler)
        
        # Additional comprehensive suppression for ALL database-related loggers
        # This catches any SQLAlchemy sub-loggers that might not be explicitly listed
        for db_logger_name in self.db_logger_names:
            db_logger = logging.getLogger(db_logger_name)
            db_logger.setLevel(logging.CRITICAL)
            db_logger.propagate = False
            while db_logger.handlers:
                db_logger.removeHandler(db_logger.handlers[0])
        
        self.logger.debug("Applied comprehensive third-party library suppression")
    
    def setup_root_logger(self):
        """Set up the root logger with proper configuration."""
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        root_logger.handlers.clear()  # Clear ALL existing handlers first
        
        self.logger.debug("Root logger configured successfully")
    
    def setup_startup_logger(self):
        """Set up startup logger for initial logging before full system is ready."""
        startup_logger = logging.getLogger("STARTUP")
        startup_logger.setLevel(logging.WARNING)  # Only show warnings and errors for startup
        startup_logger.propagate = False  # Prevent propagation to root logger
        
        # Add ONLY the colored console handler to startup logger with SIMPLE format
        try:
            from logs import ColoredConsoleHandler
            console_handler = ColoredConsoleHandler(enable_colored_logs=self.enable_colored_logs, simple_format=True)
            startup_logger.addHandler(console_handler)
            self.logger.debug("Startup logger configured successfully")
        except ImportError:
            self.logger.warning("ColoredConsoleHandler not available for startup logger")
        
        return startup_logger
    
    def setup_guild_logger(self, guild_id: str, guild_name: Optional[str] = None, level: str = "INFO") -> logging.Logger:
        """Configure logging for a specific guild following technical specifications.
        
        Sets up a logger with structured logging capabilities for Discord server.
        Implements optimized third-party library suppression while maintaining proper
        application logging levels and structured logging format.
        
        Args:
            guild_id: Discord guild ID for logger identification
            guild_name: Discord guild name for configuration tracking
            level: Minimum log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            
        Returns:
            logging.Logger: logger instance with structured logging support
            
        Note:
            - Root logger suppression is handled separately
            - Structured logging with correlation IDs and context tracking
            - Guild isolation architecture with category-based filtering
        """
        try:
            from logs import setup_enhanced_logger
            
            # Set up structured logger for the guild
            logger = setup_enhanced_logger(guild_id, guild_name, level, self.enable_colored_logs)
            
            # Add structured logging category setup
            logger.info(f"Logging system initialized for guild: {guild_id}", extra={
                "log_category": "SYSTEM",
                "mod_name": "bot_logger",
                "guild_id": guild_id,
                "user_id": "N/A",
                "correlation_id": str(uuid.uuid4())[:8]
            })
            
            self.logger.debug(f"Guild logger setup completed for guild: {guild_id}")
            return logger
            
        except ImportError:
            # Fallback if logs module is not available
            logger = logging.getLogger(f"guild_{guild_id}")
            logger.setLevel(getattr(logging, level.upper()))
            
            # Clear existing handlers
            if logger.hasHandlers():
                logger.handlers.clear()
            
            # Add console handler if enabled
            if self.enable_colored_logs and hasattr(sys.stdout, 'isatty') and sys.stdout.isatty():
                try:
                    from logs import ColoredConsoleHandler
                    console_handler = ColoredConsoleHandler(enable_colored_logs=True, simple_format=True)
                    logger.addHandler(console_handler)
                except ImportError:
                    pass
            
            return logger
    
    def setup_logging_system(self):
        """Initialize the entire logging system.
        
        This is the main entry point for setting up the complete logging configuration
        including third-party suppression, root logger setup, and startup logger.
        
        Returns:
            logging.Logger: Startup logger instance for early logging
        """
        self.logger.info("Initializing comprehensive logging system...")
        
        # Step 1: Apply comprehensive third-party suppression
        self.suppress_third_party_logs()
        
        # Step 2: Set up root logger
        self.setup_root_logger()
        
        # Step 3: Set up startup logger
        startup_logger = self.setup_startup_logger()
        
        self.logger.info("Comprehensive logging system initialized successfully")
        return startup_logger
    
    def get_logger(self, guild_id: str, guild_name: Optional[str] = None, level: str = "INFO") -> logging.Logger:
        """Get or create a logger for a specific guild.
        
        This is the unified API for getting loggers throughout the application.
        
        Args:
            guild_id: Discord guild ID
            guild_name: Discord guild name for configuration tracking
            level: Minimum log level
            
        Returns:
            logging.Logger: Configured logger instance
        """
        return self.setup_guild_logger(guild_id, guild_name, level)
    
    def get_system_logger(self) -> logging.Logger:
        """Get system-level logger for non-guild events."""
        return self.setup_guild_logger('system', 'System Logs')
    
    def apply_custom_suppression(self, suppression_rules: Dict[str, int]):
        """Apply custom suppression rules in addition to defaults.
        
        Args:
            suppression_rules: Dictionary of logger names to suppression levels
        """
        for lib_name, lib_level in suppression_rules.items():
            lib_logger = logging.getLogger(lib_name)
            lib_logger.setLevel(lib_level)
            lib_logger.propagate = False
        
        self.logger.debug(f"Applied custom suppression rules: {suppression_rules}")
    
    def is_colored_logging_enabled(self) -> bool:
        """Check if colored logging is enabled."""
        return self.enable_colored_logs
    
    def get_log_format(self, enhanced: bool = False) -> str:
        """Get the log format template.
        
        Args:
            enhanced: If True, return enhanced format with correlation ID
            
        Returns:
            Log format string
        """
        return self.enhanced_format if enhanced else self.log_format
    
    def cleanup(self):
        """Cleanup logging resources if needed."""
        # This could be expanded to handle cleanup of loggers, handlers, etc.
        self.logger.debug("LoggingConfig cleanup completed")

try:
    base_config = BaseConfig(f"{CONFIG_ROOT}/base.yaml")
except Exception as e:
    try:
        from function import func
        asyncio.create_task(func.report_error(e, "addons/settings.py/module_init"))
    except Exception:
        print(f"初始化 BaseConfig 時發生錯誤: {e}")
    base_config = BaseConfig(f"{CONFIG_ROOT}/base.yaml")

try:
    llm_config = LLMConfig(f"{CONFIG_ROOT}/llm.yaml")
except Exception as e:
    try:
        from function import func
        asyncio.create_task(func.report_error(e, "addons/settings.py/module_init"))
    except Exception:
        print(f"初始化 LLMConfig 時發生錯誤: {e}")
    llm_config = LLMConfig(f"{CONFIG_ROOT}/llm.yaml")

try:
    update_config = UpdateConfig(f"{CONFIG_ROOT}/update.yaml")
except Exception as e:
    try:
        from function import func
        asyncio.create_task(func.report_error(e, "addons/settings.py/module_init"))
    except Exception:
        print(f"初始化 UpdateConfig 時發生錯誤: {e}")
    update_config = UpdateConfig(f"{CONFIG_ROOT}/update.yaml")
try:
    music_config = MusicConfig(f"{CONFIG_ROOT}/music.yaml")
except Exception as e:
    try:
        from function import func
        asyncio.create_task(func.report_error(e, "addons/settings.py/module_init"))
    except Exception:
        print(f"初始化 MusicConfig 時發生錯誤: {e}")
    music_config = MusicConfig(f"{CONFIG_ROOT}/music.yaml")
try:
    prompt_config = PromptConfig(f"{CONFIG_ROOT}/prompt")
except Exception as e:
    try:
        from function import func
        asyncio.create_task(func.report_error(e, "addons/settings.py/module_init"))
    except Exception:
        print(f"初始化 PromptConfig 時發生錯誤: {e}")
    prompt_config = PromptConfig(f"{CONFIG_ROOT}/prompt")
try:
    memory_config = MemoryConfig(f"{CONFIG_ROOT}/memory.yaml")
except Exception as e:
    try:
        from function import func
        asyncio.create_task(func.report_error(e, "addons/settings.py/module_init"))
    except Exception:
        print(f"初始化 MemoryConfig 時發生錯誤: {e}")
    memory_config = MemoryConfig(f"{CONFIG_ROOT}/memory.yaml")

try:
    # Global LoggingConfig instance
    logging_config = LoggingConfig()
except Exception as e:
    try:
        from function import func
        asyncio.create_task(func.report_error(e, "addons/settings.py/module_init"))
    except Exception:
        print(f"初始化 LoggingConfig 時發生錯誤: {e}")
    logging_config = LoggingConfig()

__all__ = [
    "BaseConfig",
    "base_config",
    "LLMConfig",
    "llm_config",
    "UpdateConfig",
    "update_config",
    "MusicConfig",
    "music_config",
    "PromptConfig",
    "prompt_config",
    "MemoryConfig",
    "memory_config",
    "LoggingConfig",
    "logging_config",
]
