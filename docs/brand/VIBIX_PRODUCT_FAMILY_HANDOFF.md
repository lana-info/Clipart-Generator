# Vibix Product Family — handoff

Status: product naming, color system, and shared `V` application mark approved
on 2026-08-17.

## Brand architecture

`Vibix` is the umbrella brand. Every product uses the same typography, dark
graphite navigation, warm light workspace, and shared icon geometry. The
product accent changes so applications remain distinguishable in Windows,
shortcuts, installers, and marketing.

| Product | Purpose | Primary | Active / dark | Soft |
| --- | --- | --- | --- | --- |
| Vibix Images | AI image generation and processing | `#2DD4BF` | `#14B8A6` / `#0F766E` | `#CCFBF1` |
| Vibix Video | Trend research and video creation | `#FF5A3C` | `#DC3D25` | `#FFF0EC` |
| Vibix Boards | Ideas, collections, and platform-ready content | `#8B5CF6` | `#6D28D9` | `#EDE9FE` |
| Vibix Poly | The existing Poly product | `#2563EB` | `#1D4ED8` / `#14213D` | `#EAF0FF` |
| Vibix Studio | A possible unified shell for the product family | Multicolor | Product-dependent | Product-dependent |

The Poly palette is taken from the existing Poly project rather than invented
for this rebrand: primary `#2563EB`, active `#1D4ED8`, soft `#EAF0FF`, dark
navigation `#14213D`, and supporting blue `#60A5FA`.

## Shared foundation

- Graphite navigation: `#101318`.
- Warm light workspace: `#F8F7F4`.
- White surfaces: `#FFFFFF`.
- Primary text: `#17191D`.
- Muted text: `#747980`.
- Neutral border: `#E2E0DB`.
- Rounded application icon and cards with restrained shadows.
- Product name format: `Vibix Images`, `Vibix Video`, `Vibix Boards`,
  `Vibix Poly`, and `Vibix Studio`.

## Approved shared mark

The application mark is a solid white `V` with one separate dark product-color
pixel to its lower right. The pixel does not touch the letter. Its lower edge
shares the same baseline as the lowest edge of the `V`, so it reads as a final
digital point rather than a detached decoration.

Canonical geometry uses a `112 × 112` view box:

- rounded product-color tile: `x=4`, `y=4`, `width=104`, `height=104`,
  `rx=27`;
- white `V` path: `M21 28H40L54 69L68 28H86L62 82H46Z`;
- dark pixel: `x=83`, `y=69`, `width=13`, `height=13`, `rx=2.5`;
- shared lower baseline: `y=82`;
- the open space between the `V` and pixel must remain visible at every size.

The reusable SVG master is `vibix-shared-mark.svg`. It contains the Vibix
Images colors by default. For another product, keep all geometry unchanged and
replace only the tile and pixel colors according to the product table above.

## Usage rules

1. Do not change the shared icon silhouette between products; change only its
   product color treatment.
2. Do not attach the dark pixel to the `V`, move it above the shared baseline,
   or introduce additional pixels.
3. Keep product colors out of long body text. Use them for primary actions,
   selection, small status accents, illustration details, and the app icon.
4. Preserve accessible text contrast. White text is used on the strong primary
   colors; dark text is used on soft product backgrounds.
5. Use the multicolor treatment only for Vibix Studio or a family-level asset.
6. Do not use `Pinterest`, `Pin`, or a variation as a Vibix product name.
   Platform compatibility can be described inside the product interface.
7. The application subtitle for Vibix Images is
   `AI Image Generation & Processing`.

## Approved Vibix Images mode artwork

The following raster illustrations are approved product assets and must be used
without replacement in the application mode cards, the download website, and
the coordinated Windows installer artwork:

| Mode | Canonical application asset | Website copy | SHA-256 |
| --- | --- | --- | --- |
| Clipart / batch generation | `assets/mode-clipart.png` | `website/vibix-download/assets/mode-clipart-hq.png` | `4eb6d0247e6412cd19d388da2928fd058d34d5a52eb2b548dc7b6aeb95e32843` |
| Pinterest pins | `assets/mode-pinterest.png` | `website/vibix-download/assets/mode-pinterest-hq.png` | `ef221f2504f274be8849265240a287eaf8b51a252972d149b1bfa9d7afb32d96` |
| Image processing | `assets/mode-processing.png` | `website/vibix-download/assets/mode-processing-hq.png` | `4a5fb6b4804e8f6a24e3c7c61bc92317022ea8e5d91db317b230ca0f78529bed` |

The website copies must remain byte-identical to the canonical application
assets. `assets/installer-wizard-hq.png` is the approved installer composition
derived from the same visual family; its SHA-256 is
`577f19f18b35a753852081afa41b1d0139dcff642202aff03ddf098258a1c76b`.
Any intentional replacement requires explicit owner approval plus an update to
the brand handoff and branding regression hashes.

## Deliverables still pending

- Master wordmark and product lockups.
- Transparent PNG exports for future marketing surfaces.
- macOS DMG artwork, if the ZIP distribution is later replaced by a graphical installer.

Completed for Vibix Images:

- Windows multi-resolution ICO and application integration.
- Three high-resolution mode illustrations for the start screen in `assets/mode-*.png`.
- Windows Inno Setup artwork in `assets/installer-wizard-hq.png` and matching
  welcome/completion messaging.

Open `vibix-product-family.html` beside this file for the portable visual
sample.
