import io
import pytest
import fitz  # PyMuPDF
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.database import Base
from app.storage.local_storage import LocalObjectStorage, default_storage


@pytest.fixture(scope="session")
def test_engine(tmp_path_factory):
    db_file = tmp_path_factory.mktemp("db") / "test_suite.db"
    engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture(scope="function")
def db_session(test_engine):
    Session = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = Session()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture(scope="session")
def sample_pdf_bytes():
    """Generates a realistic multi-page PDF with headings, formulas, and tabular data."""
    doc = fitz.open()

    # Page 1: Chapter 1 Introduction & Definition
    p1 = doc.new_page(width=612, height=792)
    p1.insert_text((50, 60), "Chapter 1: Foundations of Machine Learning", fontsize=18)
    p1.insert_text((50, 100), "1.1 Introduction", fontsize=14)
    p1.insert_text(
        (50, 130),
        "Machine Learning is defined as the scientific study of algorithms and statistical models "
        "that computer systems use to perform a specific task without explicit instructions.",
        fontsize=11
    )
    p1.insert_text(
        (50, 180),
        "For example, spam filtering in email systems classifies messages based on historical patterns.",
        fontsize=11
    )

    # Page 2: Mathematical Formulation & Table
    p2 = doc.new_page(width=612, height=792)
    p2.insert_text((50, 60), "1.2 Linear Regression and Optimization", fontsize=14)
    p2.insert_text(
        (50, 90),
        "The objective function in ordinary least squares minimization is expressed as:",
        fontsize=11
    )
    # Display formula
    p2.insert_text((80, 130), "J(w) = \\frac{1}{2m} \\sum (h_w(x) - y)^2", fontsize=12)
    
    p2.insert_text((50, 180), "Model Performance Comparison:", fontsize=12)
    # Tabular text
    table_text = (
        "Model | Accuracy | Latency_ms\n"
        "LinearRegression | 0.84 | 1.2\n"
        "RandomForest | 0.92 | 8.5\n"
        "NeuralNetwork | 0.96 | 15.0"
    )
    p2.insert_text((50, 210), table_text, fontsize=10)

    pdf_stream = io.BytesIO()
    doc.save(pdf_stream)
    doc.close()
    return pdf_stream.getvalue()
