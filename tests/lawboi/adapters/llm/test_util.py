from lawboi.adapters.llm._util import approx_tokens


def test_approx_tokens_divides_total_length_by_four():
    assert approx_tokens("a" * 8) == 2


def test_approx_tokens_sums_multiple_texts():
    assert approx_tokens("a" * 4, "b" * 4) == 2


def test_approx_tokens_rounds_down():
    assert approx_tokens("abc") == 0
