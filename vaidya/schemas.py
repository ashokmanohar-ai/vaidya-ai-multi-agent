"""Typed, bounded Bedrock extraction contract. Schema correctness is not clinical correctness."""
from __future__ import annotations
from pydantic import BaseModel, ConfigDict, Field, field_validator

class ClinicalFinding(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    text: str=Field(min_length=1,max_length=1200)

class FormattingInstruction(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    instruction: str=Field(min_length=1,max_length=300)

class ReportExtractionSchema(BaseModel):
    model_config=ConfigDict(extra='forbid')
    findings:list[ClinicalFinding]=Field(max_length=50)
    instructions:list[FormattingInstruction]=Field(max_length=30)
    review_flags:list[str]=Field(max_length=20)

    @field_validator('review_flags', mode='before')
    @classmethod
    def normalize_review_flags(cls, values):
        """Accept the known Bedrock ``{'text': '...'}`` drift without losing warnings.

        Some otherwise valid Converse responses wrap a review flag in a
        single-field object despite the requested string-array JSON schema.
        Any other object, non-string item or missing flag remains invalid;
        there is no attempt to fabricate, reinterpret or discard clinical text.
        """
        if not isinstance(values, list):
            return values  # Let Pydantic reject a non-list response.
        normalized = []
        for item in values:
            if isinstance(item, dict):
                if set(item) != {'text'} or not isinstance(item.get('text'), str):
                    raise ValueError('Review flag objects must contain only a string text field')
                item = item['text']
            normalized.append(item)
        return normalized

    @field_validator('review_flags')
    @classmethod
    def validate_flags(cls, values):
        if not all(isinstance(v, str) and 0 < len(v.strip()) <= 300 for v in values):
            raise ValueError('Review flags must be nonempty strings up to 300 characters')
        return [v.strip() for v in values]
