# Task 3 — provider/model controls

`approved-mockup.png` is the approved full-screen Processing/Clipart layout.

The owner approved the visual direction in this conversation on 2026-08-29:
every enabled upscale shows provider, model and scale; background removal shows
only controls belonging to the selected Fal.ai model. In particular, Bria has
no BiRefNet/rembg controls, BiRefNet has variant/resolution/foreground, and
rembg has only its crop option.

Implementation checkpoint: `677147d` on
`codex/feat-3.1-clipart-chroma-advisor`. Final themed screenshot comparison is
still required before closing Task 3.

## Реализация

- [`implemented-birefnet-1120x780.png`](implemented-birefnet-1120x780.png) —
  BiRefNet показывает variant, resolution и refine foreground.
- [`implemented-bria-1120x780.png`](implemented-bria-1120x780.png) — Bria не
  показывает параметры BiRefNet или rembg.
- [`implemented-rembg-980x700.png`](implemented-rembg-980x700.png) — rembg при
  минимальном размере показывает только собственный crop control.

Offscreen matrix и payload tests подтверждают, что скрытые controls не попадают
в запрос выбранного endpoint. Windows scaling остаётся частью Task 13.
