from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Optionnels : si vides, l'utilisateur saisit les cl\u00e9s via /settings (UI)
    # et elles sont stock\u00e9es en SQLite (table `settings`).
    evoliz_public_key: Optional[str] = None
    evoliz_secret_key: Optional[str] = None
    # Optionnel : si non fourni, récupéré depuis la réponse de /api/login,
    # sinon fallback sur GET /api/v1/companies (premier résultat).
    evoliz_company_id: Optional[int] = None
    # URL de base pour les endpoints /v1 (companies, clients, buys, invoices...)
    evoliz_base_url: str = "https://www.evoliz.io/api/v1"
    # URL du endpoint d'auth (NB: pas sous /v1)
    evoliz_login_url: str = "https://www.evoliz.io/api/login"
    db_path: str = "data/rebill.db"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
