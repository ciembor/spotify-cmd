"""Validated values crossing the daemon socket boundary."""

from dataclasses import dataclass
from typing import Any, Mapping


class ProtocolError(ValueError):
    """Raised when a socket payload does not match the command protocol."""


@dataclass(frozen=True)
class CommandRequest:
    command: str
    setting: str | None = None
    type: str | None = None
    value: Any = None

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> 'CommandRequest':
        command = payload.get('command')
        if not isinstance(command, str) or not command:
            raise ProtocolError("Request requires a non-empty 'command' string.")
        for field in ('setting', 'type'):
            value = payload.get(field)
            if value is not None and not isinstance(value, str):
                raise ProtocolError(f"Request field '{field}' must be a string or null.")
        return cls(command, payload.get('setting'), payload.get('type'), payload.get('value'))

    def to_payload(self) -> dict[str, Any]:
        return {'command': self.command, 'setting': self.setting, 'type': self.type, 'value': self.value}
