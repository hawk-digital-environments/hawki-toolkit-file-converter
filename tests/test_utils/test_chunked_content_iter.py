from utils.processor import chunked_content_iter


def _collect(s, max_length=100):
    return list(chunked_content_iter(s, max_length))


def test_empty_string():
    assert _collect("") == []


def test_short_text_fits_in_one_chunk():
    assert _collect("Hello world.", max_length=100) == ["Hello world."]


def test_multiple_sentences_fit_together():
    assert _collect("Hi. Bye.", max_length=20) == ["Hi. Bye."]


def test_sentence_overflow_causes_split():
    assert _collect("Hello. World.", max_length=7) == ["Hello.", "World."]


def test_long_sentence_splits_by_words():
    assert _collect("one two three four", max_length=10) == ["one two", "three four"]


def test_single_word_exceeds_max_length():
    assert _collect("abcdefghij", max_length=3) == ["abc", "def", "ghi", "j"]


def test_long_word_mixed_with_normal_words():
    assert _collect("abc defghijklmnopqr stu", max_length=5) == [
        "abc",
        "defgh",
        "ijklm",
        "nopqr",
        "stu",
    ]


def test_exact_max_length():
    assert _collect("12345", max_length=5) == ["12345"]


def test_exceed_max_length_not_splitting_numbers():
    assert _collect("12.345", max_length=5) == ["12.345"]


def test_comma_separated_number_not_hard_split():
    assert _collect("12,345", max_length=3) == ["12,345"]


def test_comma_separated_number_with_decimal_not_hard_split():
    assert _collect("1,234.56", max_length=3) == ["1,234.56"]


def test_no_number_split():
    """Test that numbers are not split at all."""
    assert _collect("av345", max_length=2) == ["av", "345"]


def test_no_sentence_end_split():
    """Test that last character in sentence is not split to new file."""
    assert _collect("ab.cd!ef?", max_length=2) == ["ab.", "cd!", "ef?"]


def test_pure_number_not_hard_split():
    assert _collect("12345", max_length=3) == ["12345"]


def test_text_without_punctuation():
    assert _collect("hello world", max_length=20) == ["hello world"]


def test_single_character():
    assert _collect("a", max_length=10) == ["a"]


def test_whitespace_only():
    assert _collect("   ") == []
