from sqlalchemy import Column, Table
from sqlalchemy.dialects.postgresql import UUID

from app.core.db import Base

# Minimal reference to Supabase's auth.users table so our models can declare
# foreign keys to it. Not managed by our migrations, see env.py's
# include_object filter, which excludes the "auth" schema from autogenerate.
auth_users = Table(
    "users",
    Base.metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    schema="auth",
)
