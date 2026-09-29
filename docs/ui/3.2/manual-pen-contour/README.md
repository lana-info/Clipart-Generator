# Manual pen contour

Owner approved click creation and explicitly requested double-click closure,
undo hotkeys and zoom hotkeys on 2026-09-29. Uses the existing pen canvas and
native window controls. Actual 1120×780 offscreen editor captures with synthetic
art: `actual-empty.png`, `actual-open.png`, `actual-closed.png`,
`actual-removed.png`. All right-hand controls and save/back buttons remain visible.

- Click adds a point; double click or click the first point closes the outline.
- Three non-collinear points required; open outlines cannot change the mask.
- Remove inside clears enclosed alpha. Keep inside clears external alpha.
- Existing retained alpha and RGB stay unchanged; no feather is introduced.
- Points and closure support Ctrl+Z / Ctrl+Shift+Z / Ctrl+Y; applied masks use
  existing document undo history. Delete/Backspace removes the latest open point.
- Ctrl +/- zooms. Space pans. Esc cancels calculation or pending outline.
- Save does not implicitly select a destructive operation for a manual outline.
- New contour is available after applying/cancelling the previous outline.
- Automatic-contour extraction and curve editing continue to work.

74 tests passed across `test_studio_contour`, `test_studio_contour_session`,
`test_studio_contour_large`, `test_studio_contour_integration` and
`test_v3_transparency_preview`. Includes real Qt interactions and alpha/history
assertions. Full suite, native Windows and build not run. Existing 4100px-side
contour processing limit remains. Freehand tracing while holding the mouse is
not part of this click-to-place implementation.

Approved visual refinement: Remove/Keep now use paired pictograms in one row,
with short action captions and hover descriptions. Brush/pen remain icon-only.
Persistent colour/keyboard explanations were removed. New contour is now labelled
«Обвести вручную» (owner's final wording); it starts a fresh manual outline, not a second contour merged
with the automatic one. Automatic nodes remain editable with the same pen.
Updated actual captures fit 1120×780; 37 editor/integration tests passed after
this visual refinement. Native Windows remains unverified.
