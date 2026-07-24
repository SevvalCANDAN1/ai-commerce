from datetime import datetime

from beanie import Document, Indexed, PydanticObjectId


class RefreshToken(Document):
    """Stored refresh token record. Only the token hash is persisted."""

    user_id: PydanticObjectId
    token_hash: Indexed(str, unique=True)
    expires_at: datetime
    revoked: bool = False

    class Settings:
        name = "refresh_tokens"
