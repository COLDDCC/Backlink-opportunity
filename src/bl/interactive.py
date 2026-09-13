"""Single-keypress prompts.

The whole point of `bl log` is that it takes 5-10 seconds and never
requires typing free text. These helpers read one raw keypress (no
Enter needed) and map it straight to a value. When stdin isn't a TTY
(piped input, tests, CI) they fall back to reading a line so the CLI
stays scriptable.
"""
from __future__ import annotations

import sys


def _read_one_char() -> str:
    if not sys.stdin.isatty():
        line = sys.stdin.readline()
        return line[0] if line else ""
    try:
        import termios
        import tty

        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
        return ch
    except (ImportError, termios.error, OSError):
        # not a real terminal (e.g. redirected) — fall back to line read
        line = sys.stdin.readline()
        return line[0] if line else ""


def select_key(prompt: str, options: list[tuple[str, str, object]], default: object = None) -> object:
    """Show a prompt and a list of (key, label, value) options.

    Returns the value for the pressed key. Enter/space accepts `default`
    if one is given. Ctrl-C / Ctrl-D aborts (raises KeyboardInterrupt /
    EOFError, same as any other prompt).
    """
    key_map = {k.lower(): v for k, _, v in options}
    lines = [prompt]
    for k, label, _ in options:
        marker = "*" if options and default is not None and key_map.get(k.lower()) == default else " "
        lines.append(f"  [{k}]{marker} {label}")
    sys.stdout.write("\n".join(lines) + "\n> ")
    sys.stdout.flush()
    while True:
        ch = _read_one_char()
        if ch in ("\x03",):
            sys.stdout.write("\n")
            raise KeyboardInterrupt
        if ch in ("\x04", ""):
            sys.stdout.write("\n")
            raise EOFError
        if ch in ("\r", "\n", " ") and default is not None:
            sys.stdout.write(f"{ch}\n")
            return default
        if ch.lower() in key_map:
            sys.stdout.write(f"{ch}\n")
            return key_map[ch.lower()]
        # unrecognized key: re-prompt silently, no need to spam errors
        continue


def confirm_key(prompt: str, default: bool = True) -> bool:
    hint = "[Y/n]" if default else "[y/N]"
    sys.stdout.write(f"{prompt} {hint} ")
    sys.stdout.flush()
    ch = _read_one_char()
    sys.stdout.write(f"{ch}\n" if ch not in ("\r", "\n") else "\n")
    if ch.lower() == "y":
        return True
    if ch.lower() == "n":
        return False
    if ch in ("\r", "\n", ""):
        return default
    return default
