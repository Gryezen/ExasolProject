"""
tests/test_related_documents.py — database.queries.get_related_documents()
must return the *other* side of a relationship regardless of which column
(doc_id_1 or doc_id_2) the current document happens to occupy, since
DOCUMENT_RELATIONSHIPS rows are undirected in practice (see
agents/relationships.py, which only checks for an existing row in either
order before inserting a new one).
"""

from database.queries import get_related_documents, GET_RELATED_DOCUMENTS_SQL


class FakeDatabase:
    def __init__(self, rows):
        self._rows = rows
        self.last_sql = None
        self.last_params = None

    def fetchall(self, sql, params=None):
        self.last_sql = sql
        self.last_params = params
        return self._rows


def test_get_related_documents_returns_configured_rows():
    rows = [
        ("doc-2", "income_certificate.pdf", "income_certificate", "Ravi Kumar", "complete", "income_cert_to_application", 0.91),
    ]
    db = FakeDatabase(rows)

    result = get_related_documents(db, "doc-1")

    assert result == rows
    assert db.last_params == {"doc_id": "doc-1"}
    assert db.last_sql == GET_RELATED_DOCUMENTS_SQL


def test_get_related_documents_sql_resolves_either_side_of_the_relationship():
    # The whole point of the CASE expression is symmetry — assert both
    # directions are present in the query so a future edit can't silently
    # drop one side and only surface half of a citizen's case file.
    assert "r.doc_id_1 = :doc_id THEN r.doc_id_2" in GET_RELATED_DOCUMENTS_SQL
    assert "r.doc_id_1 = :doc_id OR r.doc_id_2 = :doc_id" in GET_RELATED_DOCUMENTS_SQL
