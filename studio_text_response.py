"""Shared strict text-response parser; no workflow or credential dependencies."""
import json
from studio_text_errors import TextGenerationError


def parse_text_response(data, provider):
    """Reject truncated, refused and tool-only responses; never use thoughts."""
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
