"""build_chain must compose from the new pieces without behavior change."""
from unittest.mock import patch

import app.rag as rag


def test_build_chain_composes_retriever_and_answer_chain():
    with (
        patch.object(rag, "get_retriever") as fake_retriever,
        patch.object(rag, "build_answer_chain") as fake_answer_chain,
        patch.object(rag, "create_retrieval_chain") as fake_rrc,
    ):
        fake_retriever.return_value = "RETRIEVER"
        fake_answer_chain.return_value = "STUFF"
        chain = rag.build_chain("en")
    fake_rrc.assert_called_once_with("RETRIEVER", "STUFF")
    assert chain is fake_rrc.return_value


def test_normalize_language_values():
    assert rag._normalize_language("hi") == "hi"
    assert rag._normalize_language("HI") == "hi"
    assert rag._normalize_language("en") == "en"
    assert rag._normalize_language(None) == "en"
    assert rag._normalize_language("xx") == "en"
