"""Provider-neutral text generation/pricing error contract."""


class TextGenerationError(RuntimeError):
    pass


class ComposerAIError(TextGenerationError):
    """Only fixed, safe messages cross the asynchronous UI boundary."""

    MESSAGES = {
        "auth": "Сервис отклонил API-ключ или доступ к модели. Проверьте настройки AI.",
        "payment": "Сервис сообщил о недостаточном балансе или ограничении оплаты.",
        "rate_limit": "Сервис ограничил частоту запросов. Попробуйте позже.",
        "service": "Сервис AI временно недоступен. Попробуйте позже.",
        "http": "Сервис AI отклонил запрос.",
        "timeout": "Не удалось дождаться ответа AI.",
        "network": "Не удалось получить ответ AI из-за ошибки соединения.",
        "json": "Модель не вернула полный JSON-ответ. Набор не изменён.",
        "truncated": "Ответ AI обрезан по лимиту. Полная подборка не получена.",
        "refused": "AI отказался формировать ответ или вернул вызов инструмента вместо текста.",
        "invalid_contract": "Ответ AI не соответствует формату подборки или изменяет защищённые поля.",
        "response_limit": "Ответ AI превысил допустимый размер.",
        "provider_error": "Сервис AI сообщил об ошибке обработки запроса.",
    }

    def __init__(self, code, *, http_status=None, provider_code=None, submitted=True):
        self.code = code if code in self.MESSAGES else "provider_error"
        self.http_status = http_status if type(http_status) is int and 100 <= http_status <= 599 else None
        self.provider_code = provider_code if type(provider_code) is int and 0 <= provider_code <= 999999 else None
        suffix = " Черновик сохранён; автоматического повтора нет."
        if submitted and self.code not in {"auth", "payment", "rate_limit"}:
            suffix = " Если сервис обработал запрос, возможно списание. Проверьте его в кабинете." + suffix
        super().__init__(self.MESSAGES[self.code] + suffix)


def composer_error_code(status):
    if status in (401, 403):
        return "auth"
    if status == 402:
        return "payment"
    if status == 429:
        return "rate_limit"
    if type(status) is int and 500 <= status <= 599:
        return "service"
    return "http"


__all__ = ["TextGenerationError", "ComposerAIError", "composer_error_code"]
