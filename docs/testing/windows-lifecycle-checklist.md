# Windows lifecycle checklist

- Start → progress → success leaves no running `QThread`, timer, or temporary
  `.part`/run files.
- Cancel during generation, processing, download, and update never publishes a
  partial result as success.
- Repeated Start/Stop/Close produces one terminal event.
- Closing the window during an active run completes worker teardown before exit.
- Endpoint outage produces failed/cancelled state, never cached success.

Linux offscreen smoke does not replace this packaged Windows verification.
