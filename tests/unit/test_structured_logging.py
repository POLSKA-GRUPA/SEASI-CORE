"""Unit tests: structured logging carries the four mandatory fields."""

import json
import logging

from seasi_core.observability.structured import StructuredFormatter, log_event


def _capture(record: logging.LogRecord) -> dict:
    return json.loads(StructuredFormatter().format(record))


def test_formatter_includes_mandatory_fields() -> None:
    record = logging.LogRecord(
        name="seasi.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="x",
        args=(),
        exc_info=None,
    )
    record.seasi_event = "transition.applied"
    record.seasi_fields = {
        "tenant_id": "acme",
        "workflow_id": "case.intake",
        "case_id": "case-42",
        "state": "reviewed",
    }
    parsed = _capture(record)
    assert parsed["tenant_id"] == "acme"
    assert parsed["workflow_id"] == "case.intake"
    assert parsed["case_id"] == "case-42"
    assert parsed["state"] == "reviewed"
    assert parsed["event"] == "transition.applied"


def test_missing_fields_serialize_as_none() -> None:
    record = logging.LogRecord(
        name="seasi.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="x",
        args=(),
        exc_info=None,
    )
    record.seasi_event = "workflow.started"
    parsed = _capture(record)
    assert parsed["tenant_id"] is None
    assert parsed["state"] is None


def test_log_event_emits_structured(capsys) -> None:
    log_event(
        "test.logger",
        "workflow.started",
        tenant_id="acme",
        workflow_id="w1",
        case_id="c1",
        state="intake",
    )
    line = capsys.readouterr().err.strip().splitlines()[-1]
    parsed = json.loads(line)
    assert parsed["event"] == "workflow.started"
    assert parsed["tenant_id"] == "acme"
