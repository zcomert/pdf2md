import pytest
from src.errors import DocumentError, ErrorStage, FatalBatchError, PipelineError

def test_fatal_batch_error_is_not_a_document_error():
    with pytest.raises(FatalBatchError):
        try:
            raise FatalBatchError(ErrorStage.llm, "Ollama kapalı")
        except DocumentError:
            pytest.fail("FatalBatchError, DocumentError olarak yakalanmamalı")

def test_both_share_pipeline_base():
    assert issubclass(DocumentError, PipelineError)
    assert issubclass(FatalBatchError, PipelineError)

def test_stage_accepts_string():
    err = DocumentError("parse", "encrypted")
    assert err.stage is ErrorStage.parse
    assert str(err) == "[parse] encrypted"

def test_unknown_stage_rejected():
    with pytest.raises(ValueError):
        DocumentError("unknown", "x")
