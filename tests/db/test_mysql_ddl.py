import re

from sqlalchemy import create_engine
from sqlalchemy.schema import CreateTable

from app.db.tables import Base


def _mysql_ddl() -> str:
    engine = create_engine("mysql+pymysql://u:p@localhost/db")
    parts = [
        str(CreateTable(table).compile(dialect=engine.dialect))
        for table in Base.metadata.sorted_tables
    ]
    return "\n".join(parts)


def test_mysql_ddl_no_text_column_with_default():
    ddl = _mysql_ddl()
    for line in ddl.splitlines():
        if re.search(r"\b(?:TEXT|BLOB|JSON)\b", line, flags=re.IGNORECASE) and re.search(
            r"\bDEFAULT\b", line, flags=re.IGNORECASE
        ):
            raise AssertionError(
                f"MySQL DDL line must not set DEFAULT on TEXT/BLOB/JSON: {line.strip()}"
            )


def test_mysql_ddl_blob_unique_uses_path_digest():
    ddl = _mysql_ddl()
    assert "path_digest" in ddl
    assert re.search(r"UNIQUE\s*\([^)]*path_digest", ddl, flags=re.IGNORECASE)
