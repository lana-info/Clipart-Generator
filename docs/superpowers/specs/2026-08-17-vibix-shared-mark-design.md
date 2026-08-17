# Vibix shared application mark — design specification

Status: approved by the product owner on 2026-08-17.

## Scope

This specification defines the shared application-icon mark for the Vibix
product family. It does not yet define the final wordmark, Windows ICO export,
installer artwork, or application integration.

## Design intent

The mark must remain simple, clear, and premium at desktop-icon sizes. A solid
white `V` identifies the Vibix family. One separate dark pixel to the lower
right adds a digital and generative character: it reads as the final point that
completes a result without becoming attached to the letter.

## Canonical geometry

Use a `112 × 112` SVG view box and preserve these coordinates exactly:

- background tile: rounded rectangle at `(4, 4)`, size `104 × 104`, radius `27`;
- `V`: `M21 28H40L54 69L68 28H86L62 82H46Z`;
- pixel: rounded rectangle at `(83, 69)`, size `13 × 13`, radius `2.5`;
- common lower baseline: `y=82` for both the `V` and pixel.

The pixel is a separate element. It must not touch the `V`, move to the middle
of its height, or be repeated. The negative space between both elements is part
of the approved geometry.

## Color behavior

Geometry is identical across products. Only the tile and pixel colors change:

| Product | Tile | Pixel |
| --- | --- | --- |
| Vibix Images | `#2DD4BF` | `#0F766E` |
| Vibix Video | `#FF5A3C` | `#B92D19` |
| Vibix Boards | `#8B5CF6` | `#5B21B6` |
| Vibix Poly | `#2563EB` | `#1E40AF` |

The `V` remains `#FFFFFF`. Vibix Studio may use the approved family multicolor
treatment, but it must retain the same white `V`, separate pixel, and geometry.

## Scaling and export

- Scale the complete `112 × 112` composition proportionally; do not reposition
  individual elements per export size.
- Keep the pixel visible and distinct when checking 16, 24, 32, 48, and 256 px
  raster exports.
- Use pixel-grid-aware rasterization for the Windows ICO. Optical adjustments
  are allowed only in size-specific raster masters and must not alter the
  canonical SVG.
- Preserve transparent corners outside the rounded tile.

## Acceptance criteria

- The pixel and `V` finish on the same lower baseline.
- A visible gap remains between them at all required Windows icon sizes.
- All products use identical geometry.
- Each product uses its assigned tile and dark-pixel colors.
- No additional pixels, effects, gradients, or internal details are introduced
  without a new visual approval.

## Source assets

- SVG master: `docs/brand/vibix-shared-mark.svg`.
- Product-family visual sample: `docs/brand/vibix-product-family.html`.
- Portable brand handoff: `docs/brand/VIBIX_PRODUCT_FAMILY_HANDOFF.md`.
