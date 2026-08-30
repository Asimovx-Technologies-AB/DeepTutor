from app.rag.query_engine import is_document_level_meta_query, is_document_structure_query


def test_chapter_count_is_document_structure_query():
    question = "how many chapters are there"
    assert is_document_level_meta_query(question)
    assert is_document_structure_query(question)


def test_chapter_listing_is_document_structure_query():
    assert is_document_structure_query("List all the chapters")
    assert is_document_structure_query("What is the table of contents?")


def test_unrelated_topic_is_not_document_structure_query():
    assert not is_document_structure_query("What will the weather be tomorrow?")
    assert not is_document_level_meta_query("Explain quantum computing")
