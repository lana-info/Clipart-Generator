"""Explicit, provider-specific text routes. No aliases or implicit fallbacks."""
from dataclasses import dataclass


@dataclass(frozen=True)
class TextModel:
    provider: str
    model: str
    label: str
    endpoint: str
    experimental: bool = False
    additional: bool = False
    accepts_images: bool = True
    description: str = ''


OPENROUTER_ENDPOINT = 'https://openrouter.ai/api/v1/chat/completions'
TEXT_MODELS = (
    TextModel('kie', 'gemini-3-8-flash-openai', 'Gemini 3.8 Flash',
              'https://api.kie.ai/gemini-3-8-flash-openai/v1/chat/completions',
              accepts_images=False, description='Идеи и описания. В этом подключении доступны текстовые признаки референсов.'),
    TextModel('kie', 'claude-sonnet-4-6', 'Claude Sonnet 4.6',
              'https://api.kie.ai/claude/v1/messages', accepts_images=False,
              description='Идеи и описания. В этом подключении доступны текстовые признаки референсов.'),
    TextModel('openrouter', 'google/gemini-3.8-flash', 'Gemini 3.8 Flash', OPENROUTER_ENDPOINT),
    TextModel('openrouter', 'deepseek/deepseek-v4.1-flash', 'DeepSeek V4.1 Flash', OPENROUTER_ENDPOINT),
    TextModel('openrouter', 'openai/gpt-6-sol', 'GPT-6 Sol', OPENROUTER_ENDPOINT),
    TextModel('openrouter', 'anthropic/claude-sonnet-4.6', 'Claude Sonnet 4.6', OPENROUTER_ENDPOINT),
    TextModel('openrouter', 'qwen/qwen3.5-397b-a17b', 'Qwen3.5 397B A17B', OPENROUTER_ENDPOINT),
    TextModel('openrouter', 'x-ai/grok-4.7', 'Grok 4.7', OPENROUTER_ENDPOINT, additional=True),
    TextModel('openrouter', 'openai/gpt-5.6-sol', 'GPT-5.6 Sol', OPENROUTER_ENDPOINT, additional=True),
    TextModel('openrouter', 'deepseek/deepseek-v4-flash-vision-exp',
              'DeepSeek V4 Flash Vision Exp', OPENROUTER_ENDPOINT, True, True),
    TextModel('openrouter', 'openai/gpt-5-mini', 'GPT-5 mini', OPENROUTER_ENDPOINT, additional=True),
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
