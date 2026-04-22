import pytest

from utils.processor import ElementNode, Chunk, accumulate_chunks


async def _nodes(*elems: ElementNode):
    for e in elems:
        yield e


async def _collect(nodes, max_chunk_length, has_pages):
    return [c async for c in accumulate_chunks(nodes, max_chunk_length, has_pages)]


@pytest.mark.asyncio
async def test_empty_input():
    result = await _collect(_nodes(), max_chunk_length=10, has_pages=False)
    assert result == []


@pytest.mark.asyncio
async def test_single_node_fits():
    result = await _collect(
        _nodes(ElementNode("hello", starts_new_page=False, page_number=None)),
        max_chunk_length=10,
        has_pages=False,
    )
    assert result == [Chunk("hello", None)]


@pytest.mark.asyncio
async def test_multiple_nodes_fit_in_one_chunk():
    result = await _collect(
        _nodes(
            ElementNode("ab", starts_new_page=False, page_number=None),
            ElementNode("cd", starts_new_page=False, page_number=None),
            ElementNode("ef", starts_new_page=False, page_number=None),
        ),
        max_chunk_length=10,
        has_pages=False,
    )
    assert result == [Chunk("abcdef", None)]


@pytest.mark.asyncio
async def test_overflow_flushes_buffer():
    result = await _collect(
        _nodes(
            ElementNode("abc", starts_new_page=False, page_number=None),
            ElementNode("def", starts_new_page=False, page_number=None),
            ElementNode("ghi", starts_new_page=False, page_number=None),
        ),
        max_chunk_length=5,
        has_pages=False,
    )
    assert result == [
        Chunk("abc", None),
        Chunk("def", None),
        Chunk("ghi", None),
    ]


@pytest.mark.asyncio
async def test_single_node_exceeds_max_length():
    result = await _collect(
        _nodes(ElementNode("abcdefghij", starts_new_page=False, page_number=None)),
        max_chunk_length=3,
        has_pages=False,
    )
    assert result == [
        Chunk("abc", None),
        Chunk("def", None),
        Chunk("ghi", None),
        Chunk("j", None),
    ]


@pytest.mark.asyncio
async def test_starts_new_page_flushes_buffer():
    result = await _collect(
        _nodes(
            ElementNode("ab", starts_new_page=False, page_number=1),
            ElementNode("cd", starts_new_page=True, page_number=2),
            ElementNode("ef", starts_new_page=False, page_number=2),
        ),
        max_chunk_length=100,
        has_pages=True,
    )
    assert result == [
        Chunk("ab", 1),
        Chunk("cdef", 2),
    ]


@pytest.mark.asyncio
async def test_page_tracking_with_has_pages():
    result = await _collect(
        _nodes(
            ElementNode("a", starts_new_page=False, page_number=3),
            ElementNode("b", starts_new_page=False, page_number=5),
        ),
        max_chunk_length=100,
        has_pages=True,
    )
    assert result == [Chunk("a", 3), Chunk("b", 5)]


@pytest.mark.asyncio
async def test_has_pages_false_ignores_page_numbers():
    result = await _collect(
        _nodes(
            ElementNode("a", starts_new_page=False, page_number=3),
            ElementNode("b", starts_new_page=False, page_number=5),
        ),
        max_chunk_length=100,
        has_pages=False,
    )
    assert result == [Chunk("ab", None)]


@pytest.mark.asyncio
async def test_overflow_then_oversized_node():
    result = await _collect(
        _nodes(
            ElementNode("ab", starts_new_page=False, page_number=None),
            ElementNode("cdefghijkl", starts_new_page=False, page_number=None),
        ),
        max_chunk_length=3,
        has_pages=False,
    )
    assert result == [
        Chunk("ab", None),
        Chunk("cde", None),
        Chunk("fgh", None),
        Chunk("ijk", None),
        Chunk("l", None),
    ]


@pytest.mark.asyncio
async def test_empty_content_nodes():
    """Test that empty nodes are not contained in a chunk."""
    result = await _collect(
        _nodes(
            ElementNode("", starts_new_page=False, page_number=None),
            ElementNode("hi", starts_new_page=False, page_number=None),
            ElementNode("", starts_new_page=False, page_number=None),
        ),
        max_chunk_length=10,
        has_pages=False,
    )
    assert result == [Chunk("hi", None)]


@pytest.mark.asyncio
async def test_empty_content_nodes_new_page():
    """Test that a new empty page on start does not create an empty chunk."""
    result = await _collect(
        _nodes(
            ElementNode("", starts_new_page=True, page_number=None),
            ElementNode("hi", starts_new_page=False, page_number=None),
            ElementNode("", starts_new_page=False, page_number=None),
        ),
        max_chunk_length=10,
        has_pages=False,
    )
    assert result == [Chunk("hi", None)]


@pytest.mark.asyncio
async def test_empty_content_nodes_can_create_new_page():
    """Test that a new empty page can create a new chunk."""
    result = await _collect(
        _nodes(
            ElementNode("hi", starts_new_page=False, page_number=None),
            ElementNode("", starts_new_page=True, page_number=None),
            ElementNode("there", starts_new_page=False, page_number=None),
        ),
        max_chunk_length=10,
        has_pages=False,
    )
    assert result == [Chunk("hi", None), Chunk("there", None)]
