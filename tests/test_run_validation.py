from run_validation import validate_inputs


def test_validation_requires_inputs_for_selected_mode():
    assert validate_inputs("process_only", files=[], prompts=[]) == ("files_required",)
    assert validate_inputs("generate_only", files=[], prompts=[]) == ("prompts_required",)
    assert validate_inputs("both", files=["a.png"], prompts=[{"prompt": "x"}]) == ()
