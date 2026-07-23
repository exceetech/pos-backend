from pydantic import BaseModel, Field

class ChangePasswordRequest(BaseModel):
    # Server-side floor to match the client's own minimum (ChangePasswordActivity
    # requires 6 chars). Previously unenforced here, so /security/change-password
    # and /auth/reset-password (which both use this schema) would silently accept
    # an empty or 1-character password if the request didn't come from the
    # standard client UI.
    new_password: str = Field(min_length=6)