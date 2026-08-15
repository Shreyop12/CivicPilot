from fastapi import Request

from ..main import AppComponents


def get_components(request: Request) -> AppComponents:
    return request.app.state.components


def get_conversations(request: Request) -> dict:
    return request.app.state.conversations
