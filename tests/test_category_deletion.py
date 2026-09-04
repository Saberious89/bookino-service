from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from src.db import Base
from src.main import delete_category
from src.models import AdminAuditLog, Book, Category, User


def test_delete_category_leaves_books_uncategorized(tmp_path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'category-delete.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        admin = User(username="admin", role="admin")
        category = Category(name="Admin category")
        book = Book(title="Book", category=category)
        db.add_all([admin, category, book])
        db.commit()
        category_id = category.id
        book_id = book.id

        delete_category(category_id, admin, db)

        assert db.get(Category, category_id) is None
        assert db.get(Book, book_id).category_id is None
        audit = db.scalar(
            select(AdminAuditLog).where(AdminAuditLog.action == "delete_category")
        )
        assert audit is not None
        assert audit.target_id == str(category_id)
