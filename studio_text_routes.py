"""Explicit, provider-specific text routes. No aliases or implicit fallbacks."""
from dataclasses import dataclass


@dataclass(frozen=True)
class TextModel:
    provider: str
    model: str
    label: str
    endpoint: str
    experimental: bool = False


OPENROUTER_ENDPOINT = 'https://openrouter.ai/api/v1/chat/completions'
TEXT_MODELS = (
    TextModel('kie', 'gemini-3-8-flash-openai', 'Gemini 3.8 Flash',
              'https://api.kie.ai/gemini-3-8-flash-openai/v1/chat/completions'),
    TextModel('openrouter', 'google/gemini-3.8-flash', 'Gemini 3.8 Flash', OPENROUTER_ENDPOINT),
    TextModel('openrouter', 'deepseek/deepseek-v4-flash-vision-exp',
              'DeepSeek V4 Flash Vision Exp', OPENROUTER_ENDPOINT, True),
    TextModel('openrouter', 'openai/gpt-5-mini', 'GPT-5 mini', OPENROUTER_ENDPOINT),
)


def text_models_for(provider):
    if provider not in ('kie', 'openrouter'):
        raise ValueError('Неизвестный текстовый сервис')
    return tuple(route for route in TEXT_MODELS if route.provider == provider)


def resolve_text_model(provider, model):
    for route in text_models_for(provider):
        if route.model == model:
            return route
    raise ValueError('Модель не подключена к выбранному текстовому сервису')
