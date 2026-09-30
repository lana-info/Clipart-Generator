"""Core-owned, text-only model routes and strict Composer response parsing."""
import json
from dataclasses import dataclass

from studio_text_errors import TextGenerationError


@dataclass(frozen=True)
class ComposerTextModel:
    provider: str
    model: str
    label: str
    endpoint: str


_OPENROUTER = 'https://openrouter.ai/api/v1/chat/completions'
COMPOSER_TEXT_MODELS = (
    ComposerTextModel('kie', 'gemini-3-8-flash-openai', 'Gemini 3.8 Flash',
                      'https://api.kie.ai/gemini-3-8-flash-openai/v1/chat/completions'),
    ComposerTextModel('openrouter', 'google/gemini-3.8-flash', 'Gemini 3.8 Flash', _OPENROUTER),
    ComposerTextModel('openrouter', 'deepseek/deepseek-v4.1-flash', 'DeepSeek V4.1 Flash', _OPENROUTER),
    ComposerTextModel('openrouter', 'openai/gpt-6-sol', 'GPT-6 Sol', _OPENROUTER),
    ComposerTextModel('openrouter', 'anthropic/claude-sonnet-4.6', 'Claude Sonnet 4.6', _OPENROUTER),
    ComposerTextModel('openrouter', 'qwen/qwen3.5-397b-a17b-20260216', 'Qwen3.5 397B', _OPENROUTER),
    ComposerTextModel('openrouter', 'x-ai/grok-4.7', 'Grok 4.7', _OPENROUTER),
    ComposerTextModel('openrouter', 'openai/gpt-5.6-sol', 'GPT-5.6 Sol', _OPENROUTER),
    ComposerTextModel('openrouter', 'deepseek/deepseek-v4-flash-vision-exp',
                      'DeepSeek V4 Flash Vision Exp', _OPENROUTER),
    ComposerTextModel('openrouter', 'openai/gpt-5-mini', 'GPT-5 mini', _OPENROUTER),
)


def resolve_composer_model(provider, model):
    for route in COMPOSER_TEXT_MODELS:
        if route.provider == provider and route.model == model:
            return route
    raise ValueError('Модель не подключена к конструктору промптов')


def parse_composer_response(data, provider):
    """Reject truncated, refused, tool-only and malformed JSON responses."""
    try:
        if 'choices' in data:
            choice = data['choices'][0]
            message = choice['message']
            if choice['finish_reason'] != 'stop' or message.get('refusal') or message.get('tool_calls'):
                raise ValueError
            text = message['content']
        elif provider == 'kie':
            candidate = data['candidates'][0]
            if candidate['finishReason'] != 'STOP':
                raise ValueError
            parts = candidate['content']['parts']
            if any('functionCall' in part for part in parts):
                raise ValueError
            text = ''.join(part['text'] for part in parts
                           if not part.get('thought') and 'text' in part)
        else:
            raise ValueError
        if not isinstance(text, str) or not text.strip():
            raise ValueError
        result = json.loads(text)
        if not isinstance(result, dict):
            raise ValueError
        return result
    except (KeyError, IndexError, TypeError, ValueError, AttributeError):
        raise TextGenerationError('Модель не вернула полный JSON-ответ. Набор не изменён.') from None
