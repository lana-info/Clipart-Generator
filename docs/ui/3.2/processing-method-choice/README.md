# Restored Processing choices

Actual Qt captures at 1120x780, Linux offscreen, synthetic empty project.
Existing controls restored at owner request; no new layout or processing method.
Six captures: rembg, BEN2, chroma, Fal, KIE and PhotoRoom. Chroma and rembg
captures visually inspected; existing horizontal scrolling is preserved.
Provider-specific visibility and removal on/off covered by Qt regressions.
UI colour selection is checked through build_processing_run_request.
Auto is selected for new Processing settings/recipes. Recorded generation colour
has priority; arbitrary imported files use a conservative border detector.
165 tests and 38 subtests passed, 1 Windows Real-ESRGAN availability skip.
The three supplied originals are detected as blue; no artwork is committed.
No paid call or Windows build. White is not an available chroma colour;
uncertain/neutral borders require review without a neural fallback.
