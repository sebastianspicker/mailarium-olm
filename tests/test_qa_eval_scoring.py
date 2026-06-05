from types import ModuleType

from . import _qa_eval_scoring_attachment_cases, _qa_eval_scoring_core_cases, _qa_eval_scoring_tail_cases


def _export_tests(module: ModuleType) -> None:
    for name in dir(module):
        if name.startswith("test_"):
            globals()[name] = getattr(module, name)


_export_tests(_qa_eval_scoring_attachment_cases)
_export_tests(_qa_eval_scoring_core_cases)
_export_tests(_qa_eval_scoring_tail_cases)
