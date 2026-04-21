from src.cli import _interactive_action


def test_interactive_action_classifies_quit_aliases():
    assert _interactive_action("quit") == "quit"
    assert _interactive_action("exit") == "quit"
    assert _interactive_action("q") == "quit"


def test_interactive_action_classifies_builtin_commands():
    assert _interactive_action("stats") == "stats"
    assert _interactive_action("senders") == "senders"


def test_interactive_action_defaults_to_search():
    assert _interactive_action("budget planning") == "search"
