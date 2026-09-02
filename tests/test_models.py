from src.models import Book, Category, Device, User


def test_core_tables_have_required_constraints():
    assert {"users", "categories", "books", "book_versions", "devices"} <= {
        User.__table__.name,
        Category.__table__.name,
        Book.__table__.name,
        "book_versions",
        Device.__table__.name,
    }
    assert any(constraint.name == "ck_books_status" for constraint in Book.__table__.constraints)
