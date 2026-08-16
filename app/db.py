from functools import lru_cache

from langchain_community.vectorstores import PGVector
from langchain_huggingface import HuggingFaceEmbeddings
from sqlalchemy import create_engine

from app.config import settings

COLLECTION_NAME = "scheme_docs"


@lru_cache
def get_embeddings() -> HuggingFaceEmbeddings:
    return HuggingFaceEmbeddings(model_name=settings.embedding_model)


@lru_cache
def get_engine():
    return create_engine(settings.database_url)


@lru_cache
def get_vectorstore() -> PGVector:
    return PGVector(
        collection_name=COLLECTION_NAME,
        connection_string=settings.database_url,
        embedding_function=get_embeddings(),
        pre_delete_collection=False,
    )
