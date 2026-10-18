"""SQLAlchemy models for Skillet (SQLite).

The schema mirrors supabase/migrations/20261017000001_init.sql so data can be
imported from an existing Supabase project without transformation. Array and
jsonb columns from Postgres are stored as JSON; RLS policies from Supabase are
enforced in application code (see queries.py).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import db


def utcnow() -> datetime:
    """Timezone-aware UTC now, stored naive (SQLite has no tz support)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def new_id() -> str:
    return str(uuid.uuid4())


def new_invite_token() -> str:
    return uuid.uuid4().hex + uuid.uuid4().hex


class Base(db.Model):
    __abstract__ = True


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


def track_updated_at(cls: type) -> type:
    """Mirror the Supabase `set_updated_at()` triggers."""

    @event.listens_for(cls, "before_update")
    def _touch(mapper, connection, target):  # noqa: ANN001
        target.updated_at = utcnow()

    return cls


class User(Base, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("length(email) between 3 and 255", name="ck_users_email_len"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(80), default="Chef", nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(String(512))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "email": self.email,
            "display_name": self.display_name,
            "avatar_url": self.avatar_url,
            "created_at": _json_safe(self.created_at),
            "updated_at": _json_safe(self.updated_at),
        }


track_updated_at(User)


@track_updated_at
class Cookbook(Base, TimestampMixin):
    __tablename__ = "cookbooks"
    __table_args__ = (
        CheckConstraint("length(name) between 1 and 120", name="ck_cookbooks_name_len"),
        Index("cookbooks_owner_idx", "owner_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_private: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "owner_id": self.owner_id,
            "name": self.name,
            "description": self.description,
            "is_private": bool(self.is_private),
            "created_at": _json_safe(self.created_at),
            "updated_at": _json_safe(self.updated_at),
        }


class CookbookMember(Base):
    __tablename__ = "cookbook_members"
    __table_args__ = (
        CheckConstraint("role in ('editor', 'viewer')", name="ck_members_role"),
        Index("cookbook_members_user_idx", "user_id"),
    )

    cookbook_id: Mapped[str] = mapped_column(
        ForeignKey("cookbooks.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role: Mapped[str] = mapped_column(String(7), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cookbook_id": self.cookbook_id,
            "user_id": self.user_id,
            "role": self.role,
            "created_at": _json_safe(self.created_at),
        }


@track_updated_at
class WeeklyPlan(Base, TimestampMixin):
    __tablename__ = "weekly_plans"
    __table_args__ = (
        CheckConstraint("status in ('open', 'closed')", name="ck_plans_status"),
        UniqueConstraint("cookbook_id", "week_start", name="uq_plans_cookbook_week"),
        Index("weekly_plans_cookbook_idx", "cookbook_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    cookbook_id: Mapped[str] = mapped_column(ForeignKey("cookbooks.id", ondelete="CASCADE"), nullable=False)
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    title: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(8), default="open", nullable=False)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "cookbook_id": self.cookbook_id,
            "week_start": _json_safe(self.week_start),
            "title": self.title,
            "status": self.status,
            "created_by": self.created_by,
            "created_at": _json_safe(self.created_at),
            "updated_at": _json_safe(self.updated_at),
        }


@track_updated_at
class Recipe(Base, TimestampMixin):
    __tablename__ = "recipes"
    __table_args__ = (
        CheckConstraint("length(title) between 1 and 200", name="ck_recipes_title_len"),
        CheckConstraint("servings between 1 and 100", name="ck_recipes_servings"),
        CheckConstraint("prep_minutes is null or prep_minutes >= 0", name="ck_recipes_prep"),
        CheckConstraint("cook_minutes is null or cook_minutes >= 0", name="ck_recipes_cook"),
        CheckConstraint("status in ('published', 'draft')", name="ck_recipes_status"),
        Index("recipes_cookbook_idx", "cookbook_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    cookbook_id: Mapped[str] = mapped_column(ForeignKey("cookbooks.id", ondelete="CASCADE"), nullable=False)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    photo_path: Mapped[str | None] = mapped_column(String(512))
    prep_minutes: Mapped[int | None] = mapped_column(Integer)
    cook_minutes: Mapped[int | None] = mapped_column(Integer)
    servings: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(1024))
    tags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    ingredients: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    instructions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="published", nullable=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "cookbook_id": self.cookbook_id,
            "created_by": self.created_by,
            "title": self.title,
            "description": self.description,
            "photo_path": self.photo_path,
            "prep_minutes": self.prep_minutes,
            "cook_minutes": self.cook_minutes,
            "servings": self.servings,
            "source_url": self.source_url,
            "tags": list(self.tags or []),
            "ingredients": list(self.ingredients or []),
            "instructions": list(self.instructions or []),
            "status": self.status,
            "created_at": _json_safe(self.created_at),
            "updated_at": _json_safe(self.updated_at),
        }


class PlanRecipe(Base):
    __tablename__ = "plan_recipes"
    __table_args__ = (Index("plan_recipes_recipe_idx", "recipe_id"),)

    plan_id: Mapped[str] = mapped_column(ForeignKey("weekly_plans.id", ondelete="CASCADE"), primary_key=True)
    recipe_id: Mapped[str] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"), primary_key=True)
    added_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    selected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "recipe_id": self.recipe_id,
            "added_by": self.added_by,
            "selected": bool(self.selected),
            "created_at": _json_safe(self.created_at),
        }


@track_updated_at
class Vote(Base, TimestampMixin):
    __tablename__ = "votes"
    __table_args__ = (
        CheckConstraint("length(voter_key) between 1 and 80", name="ck_votes_voter_key"),
        CheckConstraint("length(voter_name) between 1 and 60", name="ck_votes_voter_name"),
        CheckConstraint("value between -1 and 1", name="ck_votes_value"),
        UniqueConstraint("plan_id", "recipe_id", "voter_key", name="uq_votes_plan_recipe_voter"),
        Index("votes_plan_idx", "plan_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    plan_id: Mapped[str] = mapped_column(ForeignKey("weekly_plans.id", ondelete="CASCADE"), nullable=False)
    recipe_id: Mapped[str] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False)
    voter_key: Mapped[str] = mapped_column(String(80), nullable=False)
    voter_name: Mapped[str] = mapped_column(String(60), nullable=False)
    value: Mapped[int] = mapped_column(Integer, nullable=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "plan_id": self.plan_id,
            "recipe_id": self.recipe_id,
            "voter_key": self.voter_key,
            "voter_name": self.voter_name,
            "value": self.value,
            "created_at": _json_safe(self.created_at),
            "updated_at": _json_safe(self.updated_at),
        }


class Invite(Base):
    __tablename__ = "invites"
    __table_args__ = (
        CheckConstraint("kind in ('vote', 'member')", name="ck_invites_kind"),
        CheckConstraint("role is null or role in ('editor', 'viewer')", name="ck_invites_role"),
        Index("invites_cookbook_idx", "cookbook_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    cookbook_id: Mapped[str] = mapped_column(ForeignKey("cookbooks.id", ondelete="CASCADE"), nullable=False)
    token: Mapped[str] = mapped_column(String(64), unique=True, default=new_invite_token, nullable=False)
    kind: Mapped[str] = mapped_column(String(8), nullable=False)
    role: Mapped[str | None] = mapped_column(String(7))
    plan_id: Mapped[str | None] = mapped_column(ForeignKey("weekly_plans.id", ondelete="CASCADE"))
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "cookbook_id": self.cookbook_id,
            "token": self.token,
            "kind": self.kind,
            "role": self.role,
            "plan_id": self.plan_id,
            "created_by": self.created_by,
            "expires_at": _json_safe(self.expires_at),
            "revoked_at": _json_safe(self.revoked_at),
            "created_at": _json_safe(self.created_at),
        }


class PantryItem(Base):
    __tablename__ = "pantry_items"
    __table_args__ = (
        UniqueConstraint("user_id", "normalized_name", name="uq_pantry_user_normalized"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "normalized_name": self.normalized_name,
            "created_at": _json_safe(self.created_at),
        }


@track_updated_at
class GroceryList(Base, TimestampMixin):
    __tablename__ = "grocery_lists"
    __table_args__ = (Index("grocery_lists_plan_idx", "plan_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    plan_id: Mapped[str] = mapped_column(
        ForeignKey("weekly_plans.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "plan_id": self.plan_id,
            "created_by": self.created_by,
            "created_at": _json_safe(self.created_at),
            "updated_at": _json_safe(self.updated_at),
        }


class GroceryItem(Base):
    __tablename__ = "grocery_items"
    __table_args__ = (Index("grocery_items_list_idx", "list_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    list_id: Mapped[str] = mapped_column(ForeignKey("grocery_lists.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(200), nullable=False)
    qty: Mapped[float | None] = mapped_column()
    unit: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    recipe_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    checked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    excluded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    in_pantry: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_key: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "list_id": self.list_id,
            "name": self.name,
            "normalized_name": self.normalized_name,
            "qty": self.qty,
            "unit": self.unit,
            "recipe_ids": list(self.recipe_ids or []),
            "checked": bool(self.checked),
            "excluded": bool(self.excluded),
            "in_pantry": bool(self.in_pantry),
            "sort_key": self.sort_key,
            "created_at": _json_safe(self.created_at),
        }


class PasswordResetToken(Base):
    """One-time tokens for claiming accounts imported from Supabase.

    Supabase auth passwords cannot be exported, so imported users receive a
    claim link (printed by the import script) to set a local password.
    """

    __tablename__ = "password_reset_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    token: Mapped[str] = mapped_column(String(64), unique=True, default=new_invite_token, nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
