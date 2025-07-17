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
        if required and default:
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
