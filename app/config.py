from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings
from app.models import LOB


class LOBConfig(BaseModel):
    max_auto_pay_usd: float
    fraud_floor: float = Field(ge=0.0, le=1.0)
    severity_floor: float = Field(ge=0.0, le=1.0)
    fraud_hard_gate: float = Field(ge=0.0, le=1.0)


LOB_CONFIGS: dict[LOB, LOBConfig] = {
    LOB.AUTO: LOBConfig(
        max_auto_pay_usd=5_000.0,
        fraud_floor=0.15,
        severity_floor=0.30,
        fraud_hard_gate=0.85,
    ),
    LOB.HOME: LOBConfig(
        max_auto_pay_usd=2_500.0,
        fraud_floor=0.10,
        severity_floor=0.25,
        fraud_hard_gate=0.80,
    ),
    LOB.LIABILITY: LOBConfig(
        max_auto_pay_usd=0.0,   # liability never auto-pays
        fraud_floor=0.0,
        severity_floor=0.0,
        fraud_hard_gate=0.70,
    ),
}


class Settings(BaseSettings):
    llm_provider: str = "mock"
    anthropic_api_key: str = ""
    confidence_threshold: float = Field(default=0.70, ge=0.0, le=1.0)
    prompt_version: str = "v1"

    model_config = {"env_file": ".env"}

    @model_validator(mode="after")
    def check_api_key(self) -> "Settings":
        if self.llm_provider == "anthropic" and not self.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY must be set when LLM_PROVIDER=anthropic")
        return self


settings = Settings()
