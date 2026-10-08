from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    DATABASE_URL: str = "postgresql+asyncpg://turnstile:turnstile@localhost:5432/turnstile"
    PLATFORM_WALLET: str = ""
    BASE_RPC_URL: str = "https://mainnet.base.org"
    USDC_CONTRACT: str = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
    DEFAULT_PRICE_USD: str = "0.01"
    CHAIN_ID: int = 8453

    @field_validator("PLATFORM_WALLET")
    @classmethod
    def wallet_must_be_hex(cls, v: str) -> str:
        if v and not v.startswith("0x"):
            raise ValueError("PLATFORM_WALLET must start with 0x")
        return v


settings = Settings()
