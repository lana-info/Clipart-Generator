"""Read current OpenRouter tariffs; never trigger a generation to quote a price."""
from decimal import Decimal, InvalidOperation
import json
import requests

from studio_text_errors import TextGenerationError


def fetch_text_model_info(model, api_key):
    try:
        with requests.get('https://openrouter.ai/api/v1/models',
                          headers={'Authorization': f'Bearer {api_key}'},
                          timeout=20, allow_redirects=False, stream=True) as response:
            if response.status_code != 200:
                raise ValueError
            raw = bytearray()
            for chunk in response.iter_content(65536):
                raw.extend(chunk)
                if len(raw) > 8_000_000:
                    raise ValueError
            data = json.loads(raw)
        entry = next(row for row in data['data'] if row['id'] == model)
        prices = {key: Decimal(entry['pricing'][key]) for key in ('prompt', 'completion', 'request')}
        if any(not value.is_finite() or value < 0 or value > 1000 for value in prices.values()):
            raise ValueError
        if prices['request'] != 0:
            raise ValueError  # First UI supports token-only tariffs, not extra request fees.
        modalities = entry.get('architecture', {}).get('input_modalities', ())
        if not isinstance(modalities, (list, tuple)) or any(not isinstance(value, str) for value in modalities):
            modalities = ()
        return {
            **{key: float(value * (1 if key == 'request' else 1_000_000))
               for key, value in prices.items()},
            'input_modalities': tuple(modalities),
        }
    except (requests.RequestException, ValueError, KeyError, TypeError, StopIteration, InvalidOperation):
        raise TextGenerationError('Не удалось подтвердить тариф модели. Генерация не запущена.') from None


def fetch_text_tariff(model, api_key):
    info = fetch_text_model_info(model, api_key)
    return {key: info[key] for key in ('prompt', 'completion', 'request')}
