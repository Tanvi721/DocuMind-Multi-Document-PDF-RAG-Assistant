
import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import List, Tuple

import fitz
from google import genai
from google.genai import types
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

APP_DIR = Path(__file__).resolve().parent.parent
VECTORSTORE_DIRNAME = "vectorstore_v3"
COLLECTION = "multi_pdf_collection"


@lru_cache(maxsize=1)
def _get_embeddings(provider: str, model_name: str, api_key: str) -> Embeddings:
    return APIEmbeddings(provider, model_name, api_key)


class APIEmbeddings(Embeddings):
    def __init__(self, provider: str, model_name: str, api_key: str):
        self.provider = provider
        self.model_name = model_name
        if provider == "gemini":
            self.client = genai.Client(api_key=api_key)
        else:
            from openai import OpenAI

            self.client = OpenAI(api_key=api_key)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        vectors = []
        for start in range(0, len(texts), 100):
            batch = texts[start:start + 100]
            if self.provider == "gemini":
                response = self.client.models.embed_content(
                    model=self.model_name,
                    contents=batch,
                    config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT")
                )
                embeddings = response.embeddings
                if embeddings is None or len(embeddings) != len(batch):
                    raise RuntimeError("Gemini returned an incomplete document embedding batch.")
                vectors.extend([embedding.values for embedding in embeddings])
            else:
                response = self.client.embeddings.create(
                    model=self.model_name,
                    input=batch
                )
                if len(response.data) != len(batch):
                    raise RuntimeError("OpenAI returned an incomplete document embedding batch.")
                vectors.extend(
                    [item.embedding for item in sorted(response.data, key=lambda item: item.index)]
                )
        return vectors

    def embed_query(self, text: str) -> List[float]:
        if self.provider == "gemini":
            response = self.client.models.embed_content(
                model=self.model_name,
                contents=text,
                config=types.EmbedContentConfig(task_type="RETRIEVAL_QUERY")
            )
            if not response.embeddings or response.embeddings[0].values is None:
                raise RuntimeError("Gemini returned no query embedding.")
            return response.embeddings[0].values

        response = self.client.embeddings.create(
            model=self.model_name,
            input=text
        )
        if not response.data:
            raise RuntimeError("OpenAI returned no query embedding.")
        return response.data[0].embedding


class MultiDocumentRAG:

    def __init__(self):
        provider = os.getenv("LLM_PROVIDER", "gemini").lower()
        if provider not in {"gemini", "openai"}:
            raise ValueError("LLM_PROVIDER must be either 'gemini' or 'openai'.")

        if provider == "gemini" and not os.getenv("GEMINI_API_KEY"):
            raise ValueError("Set GEMINI_API_KEY in your environment or Render settings.")
        if provider == "openai" and not os.getenv("OPENAI_API_KEY"):
            raise ValueError("Set OPENAI_API_KEY in your environment or Render settings.")

        self.data_dir = Path(os.getenv("RAG_DATA_DIR", str(APP_DIR)))
        self.persist_dir = str(self.data_dir / VECTORSTORE_DIRNAME)
        embedding_provider = os.getenv("EMBEDDING_PROVIDER", "gemini").lower()
        if embedding_provider not in {"gemini", "openai"}:
            raise ValueError("EMBEDDING_PROVIDER must be either 'gemini' or 'openai'.")

        embedding_key_name = (
            "GEMINI_API_KEY" if embedding_provider == "gemini" else "OPENAI_API_KEY"
        )
        embedding_api_key = os.getenv(embedding_key_name)
        if not embedding_api_key:
            raise ValueError(f"Set {embedding_key_name} for document embeddings.")

        default_embedding_model = (
            "gemini-embedding-001"
            if embedding_provider == "gemini"
            else "text-embedding-3-small"
        )
        embedding_model = os.getenv("EMBEDDING_MODEL", default_embedding_model)
        self.embeddings = _get_embeddings(
            embedding_provider,
            embedding_model,
            embedding_api_key
        )

        self.vectorstore = None

        if os.path.isdir(self.persist_dir) and any(Path(self.persist_dir).iterdir()):
            self.vectorstore = Chroma(
                collection_name=COLLECTION,
                persist_directory=self.persist_dir,
                embedding_function=self.embeddings
            )

    # Extract text from PDF files
    def extract_pdfs(self, paths: List[str]) -> List[Document]:

        docs = []

        for path in paths:

            if not os.path.exists(path):
                raise ValueError(f"PDF file does not exist: {path}")

            try:
                with fitz.open(path) as pdf:

                    for page_no, page in enumerate(pdf, start=1):

                        text = page.get_text("text").strip()

                        if text:
                            docs.append(
                                Document(
                                    page_content=text,
                                    metadata={
                                        "source": os.path.basename(path),
                                        "page": page_no
                                    }
                                )
                            )

            except Exception as e:
                raise ValueError(
                    f"Error reading PDF {path}: {str(e)}"
                )

        return docs

    # Split and store documents
    def ingest(self, paths: List[str]) -> int:

        pages = self.extract_pdfs(paths)

        if not pages:
            raise ValueError(
                "No readable text found in PDFs. "
                "Scanned PDFs require OCR."
            )

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=900,
            chunk_overlap=150,
            separators=["\n\n", "\n", ". ", " ", ""]
        )

        chunks = splitter.split_documents(pages)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # Replace collection contents only after extraction succeeded.
        if self.vectorstore is not None:
            self.vectorstore.delete_collection()
            self.vectorstore = None

        self.vectorstore = Chroma.from_documents(
            documents=chunks,
            embedding=self.embeddings,
            collection_name=COLLECTION,
            persist_directory=self.persist_dir
        )

        return len(chunks)

    # Generate LLM response
    def _generate(
        self,
        question: str,
        context: str,
        history: str
    ) -> str:

        prompt = f"""
You are an intelligent multi-document research assistant.

RULES:
1. Answer ONLY using the supplied document context.
2. Never invent facts or numbers.
3. If information is unavailable, respond:
   "I couldn't find this information in the uploaded documents."
4. If documents contain conflicting information, explain it.
5. Cite important claims using [filename, page N].
6. Use simple, clear and concise language.
7. Use conversation history to understand follow-up questions.

CONVERSATION HISTORY:
{history}

RETRIEVED DOCUMENT CONTEXT:
{context}

USER QUESTION:
{question}

ANSWER:
"""

        provider = os.getenv("LLM_PROVIDER", "gemini").lower()

        # OpenAI provider
        if provider == "openai":

            from openai import OpenAI

            api_key = os.getenv("OPENAI_API_KEY")

            if not api_key:
                raise ValueError("OPENAI_API_KEY is missing in .env")

            client = OpenAI(api_key=api_key)

            response = client.chat.completions.create(
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                messages=[
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1
            )

            return response.choices[0].message.content

        # Gemini provider
        from google import genai

        api_key = os.getenv("GEMINI_API_KEY")

        if not api_key:
            raise ValueError("GEMINI_API_KEY is missing in .env")

        client = genai.Client(api_key=api_key)
        model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
        if model == "gemini-2.0-flash":
            logging.warning(
                "GEMINI_MODEL=gemini-2.0-flash is retired; using gemini-3.8-flash."
            )
            model = "gemini-3.8-flash"

        response = client.models.generate_content(
            model=model,
            contents=prompt
        )

        return response.text or (
            "I couldn't generate an answer."
        )

    # Answer questions using retrieved documents
    def answer(
        self,
        question: str,
        history: list
    ) -> Tuple[str, list]:

        if not question.strip():
            return "Please enter a question.", []

        if self.vectorstore is None:
            if not os.path.isdir(self.persist_dir) or not any(Path(self.persist_dir).iterdir()):
                return "Please upload and process PDF documents first.", []

            self.vectorstore = Chroma(
                collection_name=COLLECTION,
                persist_directory=self.persist_dir,
                embedding_function=self.embeddings
            )

        # Prepare recent conversation history
        history_text = "\n".join(
            f"{m['role']}: {m['content']}"
            for m in history[-6:]
        )

        # Include conversation context for follow-up questions
        query = question

        if history_text:
            query = (
                f"Previous conversation:\n{history_text}\n"
                f"Current question: {question}"
            )

        # Retrieve relevant chunks
        try:
            results = self.vectorstore.similarity_search_with_relevance_scores(
                query,
                k=5
            )
        except Exception as exc:
            raise RuntimeError(
                "Could not search the document index. Try clearing and processing it again."
            ) from exc

        filtered = [
            (doc, score)
            for doc, score in results
            if score >= 0.20
        ]

        if not filtered:
            return (
                "I couldn't find this information in the uploaded documents.",
                []
            )

        context_parts = []
        sources = []
        seen = set()

        for doc, score in filtered:

            source = doc.metadata.get("source", "Unknown PDF")
            page = doc.metadata.get("page", "?")

            context_parts.append(
                f"[{source}, page {page}]\n{doc.page_content}"
            )

            key = (source, page)

            if key not in seen:

                seen.add(key)

                preview = " ".join(
                    doc.page_content.split()
                )[:220]

                sources.append({
                    "source": source,
                    "page": page,
                    "preview": preview
                })

        # Generate final grounded response
        answer = self._generate(
            question,
            "\n\n---\n\n".join(context_parts),
            history_text
        )

        return answer, sources
