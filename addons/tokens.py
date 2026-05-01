import os
import asyncio
from addons.logging import get_logger

from dotenv import load_dotenv

load_dotenv()
log = get_logger(server_id="Bot", source=__name__)
# keep compatibility variable name used elsewhere (if any)
logger = log


class TOKENS:
    def __init__(self) -> None:
        self.token = os.getenv("TOKEN")
        self.client_id = os.getenv("CLIENT_ID")
        self.client_secret_id = os.getenv("CLIENT_SECRET_ID")
        self.sercet_key = os.getenv("SERCET_KEY")
        raw_bug_report_channel_id = os.getenv("BUG_REPORT_CHANNEL_ID")
        self.bug_report_channel_id = int(raw_bug_report_channel_id) if raw_bug_report_channel_id not in (None, "") else None
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", None)
        os.environ["ANTHROPIC_API_KEY"] = os.getenv("ANTHROPIC_API_KEY", "")
        self.openai_api_key = os.getenv("OPENAI_API_KEY", None)
        os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY", "")
        self.google_api_key = os.getenv("GOOGLE_API_KEY", None)
        os.environ["GOOGLE_API_KEY"] = os.getenv("GOOGLE_API_KEY", "")
        self.tenor_api_key = os.getenv("TENOR_API_KEY", None)
        self.vector_store_api_key = os.getenv("VECTOR_STORE_API_KEY", None)
        bot_owner_raw = os.getenv("BOT_OWNER_ID")
        try:
            self.bot_owner_id = int(bot_owner_raw) if bot_owner_raw not in (None, "") else 0
        except (ValueError, TypeError):
            self.bot_owner_id = 0

        # Validate environment variables
        self._validate_environment_variables()

    def _validate_environment_variables(self) -> None:
        """Verify all required environment variables exist and are valid; terminate if validation fails."""
        missing_vars = []
        invalid_vars = []

        # Required environment variables (direct check of actual values)
        required_vars = {
            "TOKEN": self.token,
            "CLIENT_ID": self.client_id,
            "CLIENT_SECRET_ID": self.client_secret_id,
            "SERCET_KEY": self.sercet_key,
            "BUG_REPORT_CHANNEL_ID": os.getenv("BUG_REPORT_CHANNEL_ID"),
            "BOT_OWNER_ID": os.getenv("BOT_OWNER_ID"),
        }

        for var_name, var_value in required_vars.items():
            if not var_value:
                missing_vars.append(var_name)
            elif var_name == "BUG_REPORT_CHANNEL_ID":
                try:
                    int(var_value)
                except (ValueError, TypeError):
                    invalid_vars.append(f"{var_name} (must be a valid integer)")

        # Optional but recommended API keys
        optional_api_keys = {
            "ANTHROPIC_API_KEY": self.anthropic_api_key,
            "OPENAI_API_KEY": self.openai_api_key,
            "GOOGLE_API_KEY": self.google_api_key,
        }

        for api_name, api_value in optional_api_keys.items():
            if not api_value:
                # Report warning only, do not terminate
                try:
                    from function import func
                    asyncio.create_task(
                        func.report_error(
                            Exception(f"Warning: {api_name} is not set, some features may be affected"),
                            "addons/tokens.py/_validate_environment_variables",
                        )
                    )
                except Exception:
                    # fallback log when func is unavailable
                    logger.warning(f"Warning: {api_name} is not set, some features may be affected")

        # Terminate if any required variables are missing or invalid
        if missing_vars or invalid_vars:
            error_msg = "Environment variable validation failed:\n"
            if missing_vars:
                error_msg += f"Missing variables: {', '.join(missing_vars)}\n"
            if invalid_vars:
                error_msg += f"Invalid variables: {', '.join(invalid_vars)}\n"
            error_msg += "\nPlease check your .env file and set all required environment variables."

            try:
                from function import func
                asyncio.create_task(func.report_error(Exception(error_msg), "addons/tokens.py/_validate_environment_variables"))
            except Exception:
                logger.error(error_msg)

            # Explicitly terminate to avoid running with missing configuration
            raise SystemExit(1)


try:
    tokens = TOKENS()
except SystemExit:
    # Allow SystemExit to propagate to terminate the program
    raise
except Exception as e:
    try:
        from function import func
        asyncio.create_task(func.report_error(e, "addons/tokens.py/module_init"))
    except Exception:
        logger.error(f"Error initializing TOKENS: {e}")
    tokens = None

__all__ = ["TOKENS", "tokens"]