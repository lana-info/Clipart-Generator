from provider_error_messages import friendly_provider_error


def test_fal_insufficient_credits_are_human_readable():
    category, message = friendly_provider_error("Fal.ai HTTP 402: insufficient credits")
    assert category == "insufficient_credits"
    assert "пополните баланс" in message.casefold()


def test_fal_auth_and_rate_limit_are_classified():
    assert friendly_provider_error("Fal.ai HTTP 401: unauthorized")[0] == "authentication"
    assert friendly_provider_error("Fal.ai HTTP 429: rate limit")[0] == "rate_limit"
