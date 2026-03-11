"""Tests for SQLAlchemy ORM models — structure verification (no DB needed)."""

from src.core.models import (
    Base,
    ComplianceComparison,
    ComplianceItem,
    Document,
    DocumentChunk,
    LLMCache,
    Product,
    ProductComponent,
    Tender,
    TenderRequirement,
)


def test_all_models_registered():
    """Verify all expected tables are registered in metadata."""
    table_names = set(Base.metadata.tables.keys())
    expected = {
        "products",
        "product_components",
        "tenders",
        "tender_requirements",
        "compliance_comparisons",
        "compliance_items",
        "documents",
        "document_chunks",
        "llm_cache",
    }
    assert expected.issubset(table_names), f"Missing tables: {expected - table_names}"


def test_product_table_columns():
    """Verify Product model has expected columns."""
    columns = {c.name for c in Product.__table__.columns}
    assert "id" in columns
    assert "product_name" in columns
    assert "product_family" in columns
    assert "specs" in columns
    assert "created_at" in columns


def test_tender_table_columns():
    columns = {c.name for c in Tender.__table__.columns}
    assert "project_name" in columns
    assert "client" in columns
    assert "requirements" in columns
    assert "status" in columns


def test_document_chunk_has_embedding():
    """Verify DocumentChunk has vector embedding column."""
    columns = {c.name for c in DocumentChunk.__table__.columns}
    assert "embedding" in columns
    assert "chunk_text" in columns
    assert "chunk_index" in columns


def test_llm_cache_table():
    """Verify LLMCache has the required structure."""
    columns = {c.name for c in LLMCache.__table__.columns}
    assert "cache_key" in columns
    assert "model" in columns
    assert "schema_name" in columns
    assert "result" in columns
    assert "cost_usd" in columns


def test_foreign_keys():
    """Verify foreign key relationships are set up."""
    # ProductComponent -> Product
    fks = {fk.target_fullname for fk in ProductComponent.__table__.foreign_keys}
    assert "products.id" in fks

    # TenderRequirement -> Tender
    fks = {fk.target_fullname for fk in TenderRequirement.__table__.foreign_keys}
    assert "tenders.id" in fks

    # ComplianceComparison -> Product, Tender
    fks = {fk.target_fullname for fk in ComplianceComparison.__table__.foreign_keys}
    assert "products.id" in fks
    assert "tenders.id" in fks

    # ComplianceItem -> ComplianceComparison
    fks = {fk.target_fullname for fk in ComplianceItem.__table__.foreign_keys}
    assert "compliance_comparisons.id" in fks

    # DocumentChunk -> Document
    fks = {fk.target_fullname for fk in DocumentChunk.__table__.foreign_keys}
    assert "documents.id" in fks


def test_indexes_defined():
    """Verify key indexes exist."""
    idx_names = {idx.name for idx in Product.__table__.indexes}
    assert "idx_products_specs" in idx_names

    idx_names = {idx.name for idx in Tender.__table__.indexes}
    assert "idx_tenders_reqs" in idx_names

    idx_names = {idx.name for idx in Document.__table__.indexes}
    assert "idx_documents_status" in idx_names
