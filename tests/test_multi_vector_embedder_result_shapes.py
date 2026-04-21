"""Result-shape and helper-contract tests for the multi-vector embedder."""

from __future__ import annotations

import numpy as np

from src.multi_vector_embedder import (
    MultiVectorResult,
    _convert_sparse,
    _normalize_colbert,
    _to_list_of_lists,
)


def test_to_list_of_lists_numpy():
    arr = np.array([[1.0, 2.0], [3.0, 4.0]])
    result = _to_list_of_lists(arr)
    assert isinstance(result, list)
    assert isinstance(result[0], list)
    assert result[0] == [1.0, 2.0]


def test_to_list_of_lists_already_list():
    data = [[1.0, 2.0], [3.0, 4.0]]
    assert _to_list_of_lists(data) is data


def test_to_list_of_lists_list_of_ndarray():
    data = [np.array([1.0, 2.0]), np.array([3.0, 4.0])]
    result = _to_list_of_lists(data)
    assert isinstance(result, list)
    assert isinstance(result[0], list)


def test_convert_sparse_filters_zero_weights():
    raw = [{1: 0.5, 2: 0.0, 3: 0.8}]
    result = _convert_sparse(raw)
    assert len(result) == 1
    assert 2 not in result[0]
    assert result[0][1] == 0.5
    assert result[0][3] == 0.8


def test_convert_sparse_int_keys():
    raw = [{"42": 0.9}]
    result = _convert_sparse(raw)
    assert 42 in result[0]


def test_convert_sparse_empty():
    assert _convert_sparse([]) == []


def test_normalize_colbert_numpy():
    data = [np.ones((3, 4))]
    result = _normalize_colbert(data)
    assert isinstance(result[0], np.ndarray)
    assert result[0].shape == (3, 4)


def test_normalize_colbert_plain_list():
    data = [[[1.0, 2.0], [3.0, 4.0]]]
    result = _normalize_colbert(data)
    assert isinstance(result[0], np.ndarray)


def test_multi_vector_result_defaults():
    result = MultiVectorResult(dense=[[1.0, 2.0]])
    assert result.sparse is None
    assert result.colbert is None
    assert result.dense == [[1.0, 2.0]]
