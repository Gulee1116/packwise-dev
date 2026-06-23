from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Token:
    kind: str
    value: str
    position: int


class SnbtParser:
    def __init__(self, text: str) -> None:
        self.tokens = _tokenize(text)
        self.index = 0

    def parse(self) -> Any:
        value = self._parse_value()
        if not self._at_end():
            token = self._peek()
            raise ValueError(f"Unexpected token {token.value!r} at {token.position}")
        return value

    def _parse_value(self) -> Any:
        token = self._peek()
        if token.value == "{":
            return self._parse_compound()
        if token.value == "[":
            return self._parse_list_or_typed_array()
        self.index += 1
        if token.kind == "string":
            return token.value
        return _atom(token.value)

    def _parse_compound(self) -> dict[str, Any]:
        self._expect("{")
        result: dict[str, Any] = {}
        while not self._accept("}"):
            key_token = self._peek()
            if key_token.kind not in {"identifier", "string"}:
                raise ValueError(f"Expected compound key at {key_token.position}, got {key_token.value!r}")
            self.index += 1
            self._expect(":")
            result[key_token.value] = self._parse_value()
            self._accept(",")
        return result

    def _parse_list_or_typed_array(self) -> list[Any]:
        self._expect("[")
        if self._is_typed_array_prefix():
            self.index += 1
            self._expect(";")
        values: list[Any] = []
        while not self._accept("]"):
            values.append(self._parse_value())
            self._accept(",")
        return values

    def _is_typed_array_prefix(self) -> bool:
        if self.index + 1 >= len(self.tokens):
            return False
        return self.tokens[self.index].value in {"B", "I", "L"} and self.tokens[self.index + 1].value == ";"

    def _expect(self, value: str) -> None:
        token = self._peek()
        if token.value != value:
            raise ValueError(f"Expected {value!r} at {token.position}, got {token.value!r}")
        self.index += 1

    def _accept(self, value: str) -> bool:
        if self._at_end() or self._peek().value != value:
            return False
        self.index += 1
        return True

    def _peek(self) -> Token:
        if self._at_end():
            raise ValueError("Unexpected end of SNBT")
        return self.tokens[self.index]

    def _at_end(self) -> bool:
        return self.index >= len(self.tokens)


def parse_snbt(text: str) -> Any:
    return SnbtParser(text).parse()


def _tokenize(text: str) -> list[Token]:
    tokens: list[Token] = []
    index = 0
    while index < len(text):
        char = text[index]
        if char.isspace():
            index += 1
            continue
        if char in "{}[]:;,":
            tokens.append(Token("symbol", char, index))
            index += 1
            continue
        if char in {'"', "'"}:
            value, index = _read_quoted(text, index)
            tokens.append(Token("string", value, index))
            continue
        start = index
        while index < len(text) and (not text[index].isspace()) and text[index] not in "{}[]:;,":
            index += 1
        tokens.append(Token("identifier", text[start:index], start))
    return tokens


def _read_quoted(text: str, start: int) -> tuple[str, int]:
    quote = text[start]
    index = start + 1
    chars: list[str] = []
    while index < len(text):
        char = text[index]
        if char == quote:
            return "".join(chars), index + 1
        if char == "\\":
            index += 1
            if index >= len(text):
                break
            chars.append(_unescape(text[index]))
            index += 1
            continue
        chars.append(char)
        index += 1
    raise ValueError(f"Unterminated string at {start}")


def _unescape(char: str) -> str:
    return {
        '"': '"',
        "'": "'",
        "\\": "\\",
        "n": "\n",
        "r": "\r",
        "t": "\t",
    }.get(char, char)


def _atom(value: str) -> Any:
    normalized = value.lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    numeric = value[:-1] if value[-1:] in "bBsSlLfFdD" else value
    try:
        if any(marker in numeric for marker in ".eE"):
            return float(numeric)
        return int(numeric)
    except ValueError:
        return value
