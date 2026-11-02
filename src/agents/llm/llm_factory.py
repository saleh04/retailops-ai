from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from core.config import Settings, get_settings


class LLMConfigurationError(ValueError):
    """Raised when LLM configuration is invalid."""


class LLMFactory:

    def __init__(self, config: Settings | None = None):
        self.config = config if config is not None else get_settings()
        
    def create(self) -> BaseChatModel:
        
        model_id = self.config.MODEL_ID

        if not model_id:
            raise LLMConfigurationError("MODEL_ID must be configured.")

        model_params = {
            "model": model_id,
        }

        if self.config.DEFAULT_TEMPERATURE is not None:
            model_params["temperature"] = self.config.DEFAULT_TEMPERATURE

        if self.config.DEFAULT_MAX_TOKENS is not None:
            model_params["max_tokens"] = self.config.DEFAULT_MAX_TOKENS

        if self.config.GENERATION_BACKEND == "OPENAI":

            if self.config.OPENAI_API_KEY is None:
                raise LLMConfigurationError("OPENAI_API_KEY is required.")

            model_params.update({
                "model_provider": "openai",
                "api_key": self.config.OPENAI_API_KEY.get_secret_value(),
            })

            if self.config.OPENAI_API_URL:
                model_params["base_url"] = self.config.OPENAI_API_URL

        elif self.config.GENERATION_BACKEND == "GEMINI":

            if self.config.GOOGLE_API_KEY is None:
                raise LLMConfigurationError("GOOGLE_API_KEY is required.")

            model_params.update({
                "model_provider": "google_genai",
                "api_key": self.config.GOOGLE_API_KEY.get_secret_value(),
            })

        else:
            raise LLMConfigurationError(
                f"Unsupported backend: {self.config.GENERATION_BACKEND}"
            )

        return init_chat_model(**model_params)