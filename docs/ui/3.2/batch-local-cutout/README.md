# Batch local cutout, 2026-09-29

Owner authorized batch local background removal in Processing after clarification
that it uses a local neural model without paid image API calls. Existing Files,
Goal, Processing, Results and Transparency pages are reused. One recipe is added
to the existing list: «Удалить фон с чёткими краями». Other recipes retain their
settings. Actual offscreen Qt captures use safe dummy files at 1120×780.
The pipeline retains its existing horizontal scrolling operations layout.

The recipe selects local rembg/U2Net and a cutout edge mode. The same mask helper
serves automatic-set fallback and batch processing: threshold192, binary alpha,
4px inward edge, no feather. No implicit upscale, trim, sharpening or paid calls.
U2Net is cached per worker. Initial model installation can download model data;
image bytes are not uploaded. Existing usable transparency is preserved as-is.
Empty/opaque masks fail that file; the batch continues and failed files are not
export candidates. Cancellation after inference prevents publishing the result.
Saved editor copies now update the Processing results entry.

Evidence: real processing of both owner-supplied 1536×1536 PNGs using the cached
U2Net model, 13.43s total on this Linux host. Both outputs have alpha values0/255,
retain canvas size and leave source hashes unchanged. Result/report files remain
in /tmp/clipart-batch-cutout-acceptance; private artwork is not committed here.
Visual inspection: paper can remain around fine details and enclosed holes; a
binary mask does not prove perfect segmentation. The editor remains available.

Checks:195 tests passed,33 subtests,1 Real-ESRGAN test deselected (unchanged and
not required for this no-upscale recipe). Two additional tests for editor-copy
handoff and cancellation passed. Packaging/dependency check additionally found
an existing export-workspace dependency-baseline failure:
studio_auto_clipart_flow -> studio_set_export_ui. No suppression or allowlist
change made as part of this processing task. Subsequently resolved by routing
export-view construction through RunResultsExtension; baseline test unchanged.
No paid requests, new dependencies, Windows build, commits or pushes.

## Results handoff and Windows acceptance preparation

The existing results action row adds «Обработать выбранное». Select a saved
result, including a failed processing output, then open Processing with that PNG.
Source project is saved first. The new project disables overwrite and starts no
worker. Current settings are shown for review; choose the sharp-cutout recipe
if needed. Actual1120x780 captures: actual-results-handoff.png and
actual-handoff-files.png. This is a small addition to the existing action row.

For the next separately authorized Windows build:
1. Commit/review the exact source and record its SHA before dispatch.
2. Run existing packaging/dependency gates and installed-artifact smoke through
   scripts/verify_installed_windows_artifact.ps1 using the matching installer.
3. At1120x780, open an Automatic Clipart saved result and use the handoff button.
   Confirm original set reopens, PNG is loaded, no request starts automatically.
4. Batch-process copies of the two owner PNGs with the sharp-cutout recipe.
   Check original hashes, alpha, visible edges and failed-file handling.
5. Verify local upscale actually changes dimensions while retaining alpha;
   maximize the transparency window, edit contour, undo and save a copy.
6. Reopen a failed run and retry processing without image generation; export a
   named set, verify ZIP contents and blocked close/switch while ZIP is running.
7. Check text provider/model and quote immediately before any separately
   authorized paid request. KIE dated quotes expire2026-10-29; refresh before
   release if necessary. No live compatibility or native Windows test claimed.
