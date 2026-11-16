"""Regression tests for the schema inspector (`database.schema_inspector`)."""

from __future__ import annotations

import pytest

from database.schema_inspector import (
    SchemaInspectionError,
    SchemaInspector,
    TableNotFoundError,
)


# --------------------------------------------------------------------------
# Table listing
# --------------------------------------------------------------------------
def test_list_tables_returns_the_real_tables(schema_inspector: SchemaInspector):
    tables = schema_inspector.list_tables()

    assert set(tables) == {"customers", "orders", "order_items"}
    assert "customers" in tables


def test_list_tables_is_empty_for_an_empty_database(tmp_path):
    from sqlalchemy import create_engine

    engine = create_engine(f"sqlite:///{tmp_path.as_posix()}/empty.db")
    inspector = SchemaInspector(engine)

    assert inspector.list_tables() == []

    engine.dispose()


def test_unknown_schema_is_reported(schema_inspector: SchemaInspector):
    """SQLite only knows the `main` schema."""
    with pytest.raises(SchemaInspectionError, match="Could not list database tables."):
        schema_inspector.list_tables(schema="does_not_exist")


def test_known_schema_is_accepted(schema_inspector: SchemaInspector):
    assert set(schema_inspector.list_tables(schema="main")) == {
        "customers",
        "orders",
        "order_items",
    }


# --------------------------------------------------------------------------
# Columns
# --------------------------------------------------------------------------
def test_get_table_columns_returns_names_types_and_nullability(
    schema_inspector: SchemaInspector,
):
    columns = schema_inspector.get_table_columns("customers")

    assert [column["name"] for column in columns] == [
        "id",
        "name",
        "email",
        "city",
        "signup_date",
    ]
    assert [column["type"] for column in columns] == [
        "INTEGER",
        "TEXT",
        "TEXT",
        "TEXT",
        "TEXT",
    ]
    assert [column["nullable"] for column in columns] == [
        False,
        False,
        True,
        True,
        False,
    ]


def test_get_table_columns_of_a_related_table(schema_inspector: SchemaInspector):
    columns = schema_inspector.get_table_columns("order_items")

    assert [column["name"] for column in columns] == [
        "id",
        "order_id",
        "product",
        "quantity",
        "unit_price",
    ]
    assert columns[4]["type"] == "REAL"


# --------------------------------------------------------------------------
# Keys and relationships
# --------------------------------------------------------------------------
def test_primary_key_is_reported(schema_inspector: SchemaInspector):
    relationships = schema_inspector.get_table_relationships("customers")

    assert relationships["primary_key"] == ["id"]
    assert relationships["foreign_keys"] == []


def test_foreign_keys_are_reported(schema_inspector: SchemaInspector):
    relationships = schema_inspector.get_table_relationships("orders")

    assert relationships["primary_key"] == ["id"]
    assert len(relationships["foreign_keys"]) == 1

    foreign_key = relationships["foreign_keys"][0]
    assert foreign_key["columns"] == ["customer_id"]
    assert foreign_key["referred_table"] == "customers"
    assert foreign_key["referred_columns"] == ["id"]


def test_nested_foreign_keys_are_reported(schema_inspector: SchemaInspector):
    relationships = schema_inspector.get_table_relationships("order_items")

    assert relationships["foreign_keys"][0]["referred_table"] == "orders"


# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "table_name", ["missing", "customers ", "CUSTOMERS", "sqlite_master"]
)
def test_unknown_table_raises_table_not_found(
    schema_inspector: SchemaInspector, table_name: str
):
    with pytest.raises(TableNotFoundError, match="was not found"):
        schema_inspector.get_table_columns(table_name)

    with pytest.raises(TableNotFoundError, match="was not found"):
        schema_inspector.get_table_relationships(table_name)


def test_table_not_found_error_is_a_schema_inspection_error():
    assert issubclass(TableNotFoundError, SchemaInspectionError)


def test_is_table_exists_returns_false_for_unknown_table(schema_inspector: SchemaInspector):
    assert schema_inspector.is_table_exists("missing") is False


def test_is_table_exists_returns_true_for_known_table(schema_inspector: SchemaInspector):
    assert schema_inspector.is_table_exists("customers") is True


# --------------------------------------------------------------------------
# Whole database schema
# --------------------------------------------------------------------------
def test_get_database_schema_describes_every_table(schema_inspector: SchemaInspector):
    schema = schema_inspector.get_database_schema()

    assert set(schema) == {"customers", "orders", "order_items"}

    customers = schema["customers"]
    assert [column["name"] for column in customers["columns"]][0] == "id"
    assert customers["primary_key"] == ["id"]
    assert customers["foreign_keys"] == []

    orders = schema["orders"]
    assert orders["foreign_keys"][0]["referred_table"] == "customers"
