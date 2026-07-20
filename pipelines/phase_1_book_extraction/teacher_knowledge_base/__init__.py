"""
teacher_knowledge_base/__init__.py — M6.1/M6.2 (remediated)

Public API surface for the Teacher Knowledge Base package.
"""
from .builder import build_teacher_knowledge_base, get_current_build_result
from .artifact import TeacherKnowledgeBase
from .tkb_runtime import TKBRuntime, TKBRuntimeError
from .exceptions import (
    TeacherKnowledgeBaseError,
    TKBBuildError,
    TKBValidationError,
    TKBSerializationError,
    TKBRegistrationError,
    TKBLoaderError,
    TKBBuilderError,
    TKBAmbiguityError,
)
from .state import (
    get_current_tkb_result,
    has_current_tkb_result,
    reset_all_tkb_state,
)

__all__ = [
    "build_teacher_knowledge_base",
    "get_current_build_result",
    "TeacherKnowledgeBase",
    "TKBRuntime",
    "TKBRuntimeError",
    "TeacherKnowledgeBaseError",
    "TKBBuildError",
    "TKBValidationError",
    "TKBSerializationError",
    "TKBRegistrationError",
    "TKBLoaderError",
    "TKBBuilderError",
    "TKBAmbiguityError",
    "get_current_tkb_result",
    "has_current_tkb_result",
    "reset_all_tkb_state",
]
