"""Core-owned, text-only model routes and strict Composer response parsing."""
import json
from dataclasses import dataclass

from studio_text_errors import TextGenerationError, ComposerAIError, composer_error_code


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
        if not isinstance(data, dict):
            raise ValueError
        # KIE documents business errors returned with HTTP 200.
        if provider == 'kie' and 'code' in data and str(data['code']) != '200':
            value = data['code']
            code = int(value) if type(value) is int or (isinstance(value, str) and value.isdigit() and len(value) <= 6) else None
            category = composer_error_code(code) if code in (401, 402, 403, 429) or (type(code) is int and 500 <= code <= 599) else 'provider_error'
            raise ComposerAIError(category, http_status=200, provider_code=code)
        if 'choices' in data:
            choice = data['choices'][0]
            message = choice['message']
            if choice['finish_reason'] == 'length':
                raise ComposerAIError('truncated', http_status=200)
            if message.get('refusal') or message.get('tool_calls') or choice['finish_reason'] == 'content_filter':
                raise ComposerAIError('refused', http_status=200)
            if choice['finish_reason'] != 'stop':
                raise ValueError
            text = message['content']
        elif provider == 'kie':
            candidate = data['candidates'][0]
            if candidate['finishReason'] == 'MAX_TOKENS':
                raise ComposerAIError('truncated', http_status=200)
            if candidate['finishReason'] in ('SAFETY', 'RECITATION'):
                raise ComposerAIError('refused', http_status=200)
            if candidate['finishReason'] != 'STOP':
                raise ValueError
            parts = candidate['content']['parts']
            if any('functionCall' in part for part in parts):
                raise ComposerAIError('refused', http_status=200)
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
        raise ComposerAIError('json', http_status=200) from None
