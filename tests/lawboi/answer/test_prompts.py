from lawboi.answer.prompts import format_history


def test_format_history_empty():
    assert format_history(None) == ""
    assert format_history([]) == ""


def test_format_history_renders_roles_and_content():
    history = [{"role": "user", "content": "what is the notice period?"},
               {"role": "assistant", "content": "It is 30 days."}]
    out = format_history(history)
    assert "USER: what is the notice period?" in out
    assert "ASSISTANT: It is 30 days." in out


def test_format_history_truncates_long_message():
    history = [{"role": "user", "content": "x" * 100}]
    out = format_history(history, max_chars=10)
    assert "x" * 11 not in out
    assert "[…truncated]" in out
