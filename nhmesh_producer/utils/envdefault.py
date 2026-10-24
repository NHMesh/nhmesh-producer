import argparse
import os
from typing import Any


class EnvDefault(argparse.Action):
    def __init__(
        self, envvar: str, required: bool = True, default: Any = None, **kwargs: Any
    ) -> None:
        if envvar:
            if envvar in os.environ:
                default = os.environ[envvar]
        # Only required when there is no default at all. `if default:` made any
        # falsy default (False, 0, "") mandatory - e.g. --tls with default False.
        if required and default is not None:
            required = False
        super().__init__(default=default, required=required, **kwargs)

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: Any,
        option_string: str | None = None,
    ) -> None:
        setattr(namespace, self.dest, values)
