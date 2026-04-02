"""ASGI entrypoint for the maintained REST adapter."""

from mind.interfaces.rest.app import create_app

app = create_app()
