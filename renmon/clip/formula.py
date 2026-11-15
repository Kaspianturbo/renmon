"""Translate CLIP computation formulas into python expressions.

CLIP formulas are small C-like expressions over one or more mnemonics::

    (1.0 * (_SOOT_MASS_IN_CSF_22242C)) /100
    (1.0 * (X - 2730)) /10
    (X==0x00)?(0):((X==0x20)?(0):((1.0*(X))/4))

A precedence parser preserves C operator grouping and numeric boolean semantics.
Division intentionally retains fractions for CLIP scaling formulas.
"""

from __future__ import annotations

import re

_TOKEN = re.compile(
    r"""
    \s*(?:
        (?P<hex>0[xX][0-9a-fA-F]+)
      | (?P<num>\d+\.\d+|\d+)
      | (?P<name>[A-Za-z_][A-Za-z_0-9]*)
      | (?P<op>&&|\|\||<=|>=|==|!=|<<|>>|[-+*/()?:<>&|%!])
    )
    """,
    re.VERBOSE,
)


class FormulaError(ValueError):
    pass


def _tokenize(src: str) -> list[tuple[str, str]]:
    tokens, pos = [], 0
    while pos < len(src):
        m = _TOKEN.match(src, pos)
        if not m:
            if src[pos:].strip() == "":
                break
            raise FormulaError(
                f"unexpected character at {pos}: {src[pos : pos + 12]!r}"
            )
        kind = m.lastgroup
        tokens.append((kind, m.group(kind)))
        pos = m.end()
    return tokens


class _Parser:
    def __init__(self, tokens: list[tuple[str, str]]):
        self.tokens = tokens
        self.i = 0

    def peek(self) -> str | None:
        return self.tokens[self.i][1] if self.i < len(self.tokens) else None

    def take(self) -> tuple[str, str]:
        if self.i >= len(self.tokens):
            raise FormulaError("unexpected end of expression")
        tok = self.tokens[self.i]
        self.i += 1
        return tok

    def expect(self, op: str) -> None:
        kind, value = self.take()
        if value != op:
            raise FormulaError(f"expected {op!r}, got {value!r}")

    # cond ? a : b   ->   (a) if (cond) else (b)
    def ternary(self) -> str:
        cond = self.logical_or()
        if self.peek() == "?":
            self.take()
            then = self.ternary()
            self.expect(":")
            other = self.ternary()
            return f"(({then}) if ({cond}) else ({other}))"
        return cond

    _PRECEDENCE = {
        "||": 1,
        "&&": 2,
        "|": 3,
        "&": 4,
        "==": 5,
        "!=": 5,
        "<": 6,
        ">": 6,
        "<=": 6,
        ">=": 6,
        "<<": 7,
        ">>": 7,
        "+": 8,
        "-": 8,
        "*": 9,
        "/": 9,
        "%": 9,
    }

    def logical_or(self) -> str:
        return self.binary(1)

    def binary(self, minimum: int) -> str:
        left = self.unary()
        while self._PRECEDENCE.get(self.peek(), 0) >= minimum:
            op = self.take()[1]
            right = self.binary(self._PRECEDENCE[op] + 1)
            if op in ("&&", "||"):
                py_op = "and" if op == "&&" else "or"
                left = f"((({left}) != 0) {py_op} (({right}) != 0))"
            else:
                left = f"(({left}) {op} ({right}))"
        return left

    def unary(self) -> str:
        if self.peek() in ("-", "+"):
            op = self.take()[1]
            return f"({op}{self.unary()})"
        if self.peek() == "!":
            self.take()
            return f"(not {self.unary()})"
        return self.primary()

    def primary(self) -> str:
        kind, value = self.take()
        if value == "(":
            inner = self.ternary()
            self.expect(")")
            return f"({inner})"
        if kind in ("num", "hex", "name"):
            return value
        raise FormulaError(f"unexpected token {value!r}")


def to_python(source: str, mnemonics: list[str]) -> str:
    """Rewrite a CLIP formula, renaming each mnemonic to ``m0``, ``m1``, ...

    Division is forced to float so integer scaling like ``(X-2730)/10`` keeps
    its fraction, matching how CLIP means it.
    """

    text = source.replace("&amp;", "&").strip()

    # longest first: some mnemonic names are prefixes of others
    for index, name in enumerate(sorted(mnemonics, key=len, reverse=True)):
        text = text.replace(name, f" m{mnemonics.index(name)} ")

    parser = _Parser(_tokenize(text))
    expression = parser.ternary()
    if parser.i != len(parser.tokens):
        raise FormulaError(f"trailing tokens in {source!r}")
    return expression
