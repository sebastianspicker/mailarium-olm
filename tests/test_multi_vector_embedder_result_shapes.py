"""Provider-neutral result-shape tests."""

from __future__ import annotations

import numpy as np

from mailarium.multi_vector_embedder import MultiVectorResult, _to_list_of_lists


def test_to_list_of_lists_converts_numpy():
    assert _to_list_of_lists(np.array([[1.0, 2.0]])) == [[1.0, 2.0]]


def test_to_list_of_lists_preserves_python_lists():
    data = [[1.0, 2.0]]
    assert _to_list_of_lists(data) is data


def test_result_defaults_to_no_sparse_lane():
    result = MultiVectorResult(dense=[[1.0]])
    assert result.sparse is None
