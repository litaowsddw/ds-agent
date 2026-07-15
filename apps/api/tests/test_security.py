from apps.api.app.core.security import mask_api_key


def test_mask_api_key_keeps_safe_prefix_and_suffix_without_exposing_key() -> None:
    api_key = "sk-test-provider-key"

    masked = mask_api_key(api_key)

    assert masked == "sk-tes...-key"
    assert masked != api_key
    assert api_key not in masked
