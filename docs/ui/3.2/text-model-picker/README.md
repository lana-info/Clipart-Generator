# Text model picker, 2026-09-29

Owner approved the previous full-context model-tab mockups, then requested and
approved dropdowns with five main choices and an additional-model group.
Actual full Studio 1120×780 offscreen captures: `actual-ideas.png`,
`actual-openrouter.png`, `actual-kie.png`, `actual-model-list.png`.
The two tabs and provider/model selection match the approved flow; the dropdown
replaces the earlier radio list. No Windows native acceptance or paid calls ran.

OpenRouter main routes: Gemini 3.8 Flash, DeepSeek V4.1 Flash, GPT-6 Sol,
Claude Sonnet 4.6, Qwen3.5 397B A17B (dated checkpoint). Additional routes:
Grok 4.7, GPT-5.6 Sol, DeepSeek V4 Flash Vision Exp and GPT-5 mini. Old project
routes remain valid. Prices and actual image capabilities are checked via
OpenRouter's model catalog before generation. No implicit model fallback.

Automatic mode preserves the saved provider instead of forcing OpenRouter.
The model provides object ideas/descriptions; final prompts still incorporate
local style/palette/background rules. Reference-image transmission defaults off,
includes only active references, uses existing hash/size/cost confirmation, and
is cleared after accepting or declining that confirmation.

KIE Claude uses the documented `/claude/v1/messages` request and native response,
with max_tokens=16000, no tools, no retries, and only text inputs in this adapter.
Published KIE prices verified 2026-09-29: $0.850 input/$4.275 output per million
from https://kie.ai/ru . This dated estimate expires 2026-10-29; it is not a live
quote or a hard cost cap. Gemini KIE remains blocked because a reliable numeric
tariff could not be confirmed. This is an unresolved technical limitation.

Sources:
- https://docs.kie.ai/market/claude/claude-sonnet-4-6.md
- https://docs.kie.ai/market/gemini/gemini-3-8-flash-openai.md
- https://openrouter.ai/deepseek/deepseek-v4.1-flash
- https://openrouter.ai/openai/gpt-6-sol/providers
- https://openrouter.ai/qwen/qwen3.5-397b-a17b-20260216
- https://openrouter.ai/x-ai/grok-4.7/

Verification: 69 tests passed plus 13 subtests across planning, text adapter,
automatic workflow and reference upgrade. Additional focused verification is
recorded in STATE.md. Full suite and native Windows remain unrun for this change.
