import sys
import time
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.rag.pdf_loader import SmartRegulationLoader
from app.rag.vector_store import ChromaVectorManager


def main() -> int:
    started_at = time.perf_counter()
    loader = SmartRegulationLoader()
    pdf_paths = sorted(loader.docs_dir.glob("*.pdf"))
    if not pdf_paths:
        print(f"No PDF regulations found in {loader.docs_dir}.")
        print("Place official regulation PDFs in backend/regulation_docs and run ingestion again.")
        return 1

    pages = []
    processed_files = []
    for pdf_path in pdf_paths:
        print(f"Extracting: {pdf_path.name}")
        extracted_pages = loader.extract_pdf_pages(str(pdf_path))
        pages.extend(extracted_pages)
        processed_files.append(pdf_path.name)
        print(f"  Pages extracted: {len(extracted_pages)}")

    chunks = loader.smart_chunk_text(pages)
    if not chunks:
        print("No text chunks were extracted; the vector index was not changed.")
        return 1

    vector_manager = ChromaVectorManager(
        persist_directory=str(BACKEND_DIR / "ml_models" / "vector_index"),
        collection_name="jkn_regulations",
    )
    inserted_count = vector_manager.insert_chunks(chunks, batch_size=100)
    elapsed = time.perf_counter() - started_at

    print("\nIngestion complete")
    print(f"Documents processed: {len(processed_files)}")
    for file_name in processed_files:
        print(f"  - {file_name}")
    print(f"Pages extracted: {len(pages)}")
    print(f"New or updated vectors: {inserted_count}")
    print(f"Total ChromaDB chunks: {vector_manager.count}")
    print(f"Index directory: {vector_manager.persist_directory}")
    print(f"Elapsed time: {elapsed:.2f} seconds")

    test_query = "Sistoskopi dan TURP apakah boleh ditagihkan bersama?"
    results = vector_manager.query_similar_regulations(test_query, top_k=3)
    print(f"\nTest query: {test_query}")
    for result in results:
        print(
            f"  {result['source_document']} page {result['page_number']} "
            f"score={result['similarity_score']:.4f}"
        )
        print(f"    {' '.join(result['text'].split())[:240]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())