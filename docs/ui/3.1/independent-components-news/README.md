# Approved Studio news UI, 2026-09-23

Owner approved: «Да, реализовать так». Synthetic content only, 1120×780.
The separate component update row was rejected and is not implemented.

| State | Approved mockup | Actual implementation |
| --- | --- | --- |
| Home, populated | [Mockup](home-news.png) | [Qt](home-populated-actual-1120x780.png) |
| Home, empty | [Mockup](home-empty.png) | [Qt](home-empty-actual-1120x780.png) |
| Home, offline | [Mockup](home-offline.png) | [Qt](home-offline-actual-1120x780.png) |
| Admin editor | [Mockup](admin-news.png) | [Chrome](admin-news-actual.png) |

Actual views were compared with the approved layout. Home retains existing cards
and a compact news panel. Admin retains the existing service design and adds the
approved side editor. Offscreen Qt is Linux evidence, not Windows acceptance.
Reproduce home screenshots with `scripts/preview_studio_news.py <output-dir>`.
Backend `docs/verification/check_studio_news_browser.py` uses actual admin/news
source with a synthetic transport; Chrome verifies editing, publication/withdrawal,
validation, duplicate submission, text escaping, network failure and navigation.
Real protected HTTP and signed HTTPS routes are covered separately by integration.
