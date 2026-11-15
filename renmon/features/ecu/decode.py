"""Turn a raw ECU response into a parameter value.

Two steps, both mirroring how CLIP defines them:

1. pull the raw integer out of the response using startByte/startBit/bitsLength
2. feed it through the parameter's formula
"""

from __future__ import annotations

import ast
from typing import Sequence

_ALLOWED_NODES = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.IfExp,
    ast.Compare,
    ast.BoolOp,
    ast.And,
    ast.Or,
    ast.Not,
    ast.Name,
    ast.Load,
    ast.Constant,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Mod,
    ast.LShift,
    ast.RShift,
    ast.BitAnd,
    ast.BitOr,
    ast.USub,
    ast.UAdd,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.Gt,
    ast.LtE,
    ast.GtE,
)

_SIGNED = {"SNUM8": 0x100, "SNUM16": 0x10000, "SNUM32": 0x100000000}


class DecodeError(ValueError):
    pass


def compile_formula(expression: str):
    """Compile a formula, rejecting anything beyond plain arithmetic."""

    tree = ast.parse(expression, mode="eval")
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise DecodeError(
                f"disallowed construct {type(node).__name__} in {expression!r}"
            )
    return compile(tree, "<formula>", "eval")


def extract_bits(payload: bytes, start_byte: int, start_bit: int, bits: int) -> int:
    """Pull an unsigned integer out of a response.

    ``start_byte`` is 1 based and counts from the service id, exactly as CLIP
    stores it, so a ``62 24 A9 xx xx xx`` reply has its first data byte at 4.
    """

    index = start_byte - 1
    span = (bits + start_bit - 1) // 8 + 1
    if index < 0 or index + span > len(payload):
        raise DecodeError(
            f"response too short: need bytes {index}..{index + span} of {len(payload)}"
        )

    raw = int.from_bytes(payload[index : index + span], "big")
    shift = ((span + 1) * 8 - (bits + start_bit)) % 8
    return (raw >> shift) & ((1 << bits) - 1)


def apply_sign(value: int, kind: str) -> int:
    span = _SIGNED.get(kind)
    if span and value > span // 2 - 1:
        return value - span
    return value


def evaluate(code, values: Sequence[float]) -> float:
    scope = {f"m{i}": v for i, v in enumerate(values)}
    return eval(code, {"__builtins__": {}}, scope)  # noqa: S307 - AST is whitelisted
