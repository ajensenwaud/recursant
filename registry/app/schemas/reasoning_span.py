"""Marshmallow schemas for reasoning span submission and response."""

from marshmallow import Schema, fields, validate


class ReasoningSpanSchema(Schema):
    """Single reasoning span within a trace."""

    task_id = fields.String(required=True, validate=validate.Length(min=1, max=255))
    agent_name = fields.String(required=True, validate=validate.Length(min=1, max=255))
    span_type = fields.String(
        required=True,
        validate=validate.OneOf(
            ["tool_call", "decision", "observation", "thought", "retrieval"]
        ),
    )
    span_name = fields.String(required=True, validate=validate.Length(min=1, max=255))
    input_data = fields.Raw(allow_none=True, load_default=None)
    output_data = fields.Raw(allow_none=True, load_default=None)
    start_time = fields.DateTime(required=True)
    end_time = fields.DateTime(allow_none=True, load_default=None)
    duration_ms = fields.Float(allow_none=True, load_default=None)
    parent_span_id = fields.UUID(allow_none=True, load_default=None)
    trace_id = fields.String(allow_none=True, load_default=None, validate=validate.Length(max=64))
    metadata = fields.Raw(allow_none=True, load_default=None)


class ReasoningSpanSubmitSchema(Schema):
    """Batch submission of reasoning spans."""

    spans = fields.List(fields.Nested(ReasoningSpanSchema), required=True)


class ReasoningSpanResponseSchema(Schema):
    """Response schema for a reasoning span from the database."""

    id = fields.UUID(dump_only=True)
    tenant_id = fields.String()
    task_id = fields.String()
    trace_id = fields.String(allow_none=True)
    agent_name = fields.String()
    span_type = fields.String()
    span_name = fields.String()
    input_data = fields.Raw(allow_none=True)
    output_data = fields.Raw(allow_none=True)
    start_time = fields.DateTime()
    end_time = fields.DateTime(allow_none=True)
    duration_ms = fields.Float(allow_none=True)
    parent_span_id = fields.UUID(allow_none=True)
    metadata = fields.Method("get_metadata")
    created_at = fields.DateTime()

    def get_metadata(self, obj):
        return obj.metadata_
