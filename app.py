import logging
import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from src.rag import MultiDocumentRAG


load_dotenv()

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("RAG_DATA_DIR", str(APP_DIR)))
UPLOAD_DIR = DATA_DIR / "data" / "uploads"
VECTOR_DIR = DATA_DIR / "vectorstore_v2"
DEMO_DIR = APP_DIR / "data" / "sample_pdfs"

st.set_page_config(page_title="DocuMind | Multi-PDF RAG", page_icon="📚", layout="wide")
st.title("📚 DocuMind — Intelligent Multi-Document RAG")
st.caption("Upload reports, ask questions across documents, and inspect source citations.")

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "doc_count" not in st.session_state:
    st.session_state.doc_count = 0
if "chunk_count" not in st.session_state:
    st.session_state.chunk_count = 0

with st.sidebar:
    st.header("Document library")
    uploaded = st.file_uploader(
        "Upload one or more PDF files", type=["pdf"], accept_multiple_files=True
    )
    if st.button("Process documents", type="primary", use_container_width=True):
        if not uploaded:
            st.warning("Please upload at least one PDF.")
        else:
            UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
            saved = []
            for file in uploaded:
                safe_name = Path(file.name).name
                path = UPLOAD_DIR / safe_name
                path.write_bytes(file.getvalue())
                saved.append(str(path))
            try:
                with st.spinner("Extracting, chunking and indexing PDFs..."):
                    rag = MultiDocumentRAG()
                    count = rag.ingest(saved)
                st.session_state.doc_count = len(saved)
                st.session_state.chunk_count = count
                st.session_state.chat_history = []
                st.success(f"Indexed {len(saved)} PDF(s) into {count} searchable chunks.")
            except Exception as exc:
                logging.exception("Could not process uploaded PDFs")
                st.error(f"Could not process the PDFs: {exc}")

    st.divider()
    st.subheader("Index status")
    st.write(f"Documents processed: **{st.session_state.doc_count}**")
    st.write(f"Chunks indexed: **{st.session_state.chunk_count}**")
    if st.button("Clear chat history"):
        st.session_state.chat_history = []
    if st.button("Clear vector index"):
        import shutil

        import shutil

        shutil.rmtree(VECTOR_DIR, ignore_errors=True)
        shutil.rmtree(UPLOAD_DIR, ignore_errors=True)
        st.session_state.doc_count = 0
        st.session_state.chunk_count = 0
        st.session_state.chat_history = []
        st.rerun()

st.info("Process PDFs first.")
demo_files = sorted(DEMO_DIR.glob("*.pdf"))
if demo_files:
    with st.expander("Try the fictional demo reports"):
        st.write("Download these sample reports and upload them above to explore the app.")
        for demo_file in demo_files:
            st.download_button(
                f"Download {demo_file.name}",
                data=demo_file.read_bytes(),
                file_name=demo_file.name,
                mime="application/pdf",
                key=f"demo-{demo_file.name}",
            )

for item in st.session_state.chat_history:
    with st.chat_message(item["role"]):
        st.markdown(item["content"])
        if item.get("sources"):
            with st.expander("Source references"):
                for source in item["sources"]:
                    st.markdown(
                        f"- **{source['source']}**, page {source['page']} — {source['preview']}"
                    )

question = st.chat_input("Ask a question about your uploaded reports...")
if question:
    st.session_state.chat_history.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    if not VECTOR_DIR.exists() or not any(VECTOR_DIR.iterdir()):
        st.warning("Upload and process PDFs before asking questions.")
    else:
        with st.chat_message("assistant"):
            try:
                with st.spinner("Searching documents and preparing an answer..."):
                    rag = MultiDocumentRAG()
                    history = st.session_state.chat_history[:-1]
                    answer, sources = rag.answer(question, history)
                st.markdown(answer)
                if sources:
                    with st.expander("Source references", expanded=True):
                        for source in sources:
                            st.markdown(
                                f"- **{source['source']}**, page {source['page']} — {source['preview']}"
                            )
                st.session_state.chat_history.append(
                    {"role": "assistant", "content": answer, "sources": sources}
                )
            except Exception as exc:
                st.error(f"Could not answer this question: {exc}")
