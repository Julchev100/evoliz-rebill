"""HTTP Basic Auth pour prot\u00e9ger l'app en ligne.

Si `APP_PASSWORD` n'est pas d\u00e9fini (mode local), la d\u00e9pendance ne fait rien.
Sinon, demande user/password \u00e0 chaque requ\u00eate (le navigateur les m\u00e9morise).
"""

import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from .config import settings

_security = HTTPBasic(auto_error=False)


def require_auth(
    credentials: HTTPBasicCredentials = Depends(_security),
) -> None:
    if not settings.app_password:
        return  # mode local, pas d'auth
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Auth requise",
            headers={"WWW-Authenticate": 'Basic realm="evoliz-rebill"'},
        )
    user_ok = secrets.compare_digest(credentials.username, settings.app_user)
    pass_ok = secrets.compare_digest(credentials.password, settings.app_password)
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Identifiants invalides",
            headers={"WWW-Authenticate": 'Basic realm="evoliz-rebill"'},
        )
