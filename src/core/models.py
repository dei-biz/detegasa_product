"""SQLAlchemy ORM models for the compliance system."""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    pass


# ── Products ─────────────────────────────────────────────────────────────────


class Product(Base):
    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    product_family: Mapped[str] = mapped_column(String(50), default="OWS")
    specs: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("NOW()"),
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        onupdate=text("NOW()"),
    )

    # Relationships
    components: Mapped[list["ProductComponent"]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_products_specs", "specs", postgresql_using="gin"),
    )


class ProductComponent(Base):
    __tablename__ = "product_components"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
    )
    component_tag: Mapped[str | None] = mapped_column(String(50))
    component_type: Mapped[str | None] = mapped_column(String(50))
    specs: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # Relationships
    product: Mapped["Product"] = relationship(back_populates="components")


# ── Tenders ──────────────────────────────────────────────────────────────────


class Tender(Base):
    __tablename__ = "tenders"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    project_name: Mapped[str] = mapped_column(String(255), nullable=False)
    client: Mapped[str | None] = mapped_column(String(255))
    contractor: Mapped[str | None] = mapped_column(String(255))
    requirements: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("NOW()"),
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        onupdate=text("NOW()"),
    )

    # Relationships
    requirements_list: Mapped[list["TenderRequirement"]] = relationship(
        back_populates="tender",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_tenders_reqs", "requirements", postgresql_using="gin"),
    )


class TenderRequirement(Base):
    __tablename__ = "tender_requirements"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    tender_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenders.id", ondelete="CASCADE"),
        nullable=False,
    )
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    requirement_text: Mapped[str] = mapped_column(Text, nullable=False)
    mandatory: Mapped[bool] = mapped_column(Boolean, default=True)
    source_document: Mapped[str | None] = mapped_column(String(255))
    source_section: Mapped[str | None] = mapped_column(String(50))
    extracted_values: Mapped[dict | None] = mapped_column(JSONB)

    # Relationships
    tender: Mapped["Tender"] = relationship(back_populates="requirements_list")

    __table_args__ = (
        Index("idx_tender_reqs_category", "category"),
    )


# ── Compliance ───────────────────────────────────────────────────────────────


class ComplianceComparison(Base):
    __tablename__ = "compliance_comparisons"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id"),
        nullable=False,
    )
    tender_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenders.id"),
        nullable=False,
    )
    overall_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    result: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("NOW()"),
    )

    # Relationships
    items: Mapped[list["ComplianceItem"]] = relationship(
        back_populates="comparison",
        cascade="all, delete-orphan",
    )


class ComplianceItem(Base):
    __tablename__ = "compliance_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    comparison_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("compliance_comparisons.id", ondelete="CASCADE"),
        nullable=False,
    )
    category: Mapped[str | None] = mapped_column(String(50))
    status: Mapped[str | None] = mapped_column(String(30))
    product_value: Mapped[str | None] = mapped_column(Text)
    tender_value: Mapped[str | None] = mapped_column(Text)
    gap_description: Mapped[str | None] = mapped_column(Text)
    modification_needed: Mapped[str | None] = mapped_column(Text)
    estimated_cost_delta: Mapped[float | None] = mapped_column(Numeric(12, 2))
    risk_level: Mapped[str | None] = mapped_column(String(20))

    # Relationships
    comparison: Mapped["ComplianceComparison"] = relationship(back_populates="items")

    __table_args__ = (
        Index("idx_compliance_items_status", "status"),
    )


# ── Documents & Embeddings ───────────────────────────────────────────────────


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    document_type: Mapped[str | None] = mapped_column(String(50))
    parent_entity_type: Mapped[str | None] = mapped_column(String(20))
    parent_entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    processing_status: Mapped[str] = mapped_column(String(20), default="pending")
    extracted_text: Mapped[str | None] = mapped_column(Text)
    extracted_json: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("NOW()"),
    )

    # Relationships
    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_documents_status", "processing_status"),
    )


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer)
    section_title: Mapped[str | None] = mapped_column(String(255))
    embedding = mapped_column(Vector(1536))
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB)

    # Relationships
    document: Mapped["Document"] = relationship(back_populates="chunks")


# ── LLM Cache ────────────────────────────────────────────────────────────────


class LLMCache(Base):
    __tablename__ = "llm_cache"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    cache_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    schema_name: Mapped[str] = mapped_column(String(100), nullable=False)
    result: Mapped[dict] = mapped_column(JSONB, nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[float | None] = mapped_column(Numeric(8, 4))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("NOW()"),
    )
