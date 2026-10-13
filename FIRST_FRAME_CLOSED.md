# CLOSED first-preview observation patch

Base: 13e9a1ed63c6e7744803419f27e429a759df1209. Local draft only; no native run, workflow dispatch, push, signing, archive, or release authorization.

This adds observation to the existing seeded picker test, not another harness. Selection callback, PhotoKit input, preview render completion, and attached-canvas candidate remain separate events. Only a successful screenshot pixel assertion is displayed-preview evidence; Done enabled and container onAppear are insufficient.

The observed screenshot completion is an upper bound, including automation/capture overhead, not the physical first display scanout. The candidate never claims display. Synthetic composition fixtures have independently known white top-left, black bottom-right, and distinct body colors. Unsupported/ambiguous fixture dimensions fail closed. Existing fixture membership/selected-original checks remain mandatory.

The existing 3-second picker-entry gate is unchanged. No new product latency SLO is invented. The first-preview interval is reported, while missing, stale, reordered, or non-pixel evidence fails the diagnostic. A separate review must authorize native execution and choose a product performance budget before claiming performance acceptance.

Pixel addressing uses the actual screenshot CGImage dimensions divided by the captured app point frame, so display scale is not assumed. UIImage orientation must be `.up`; app frame, canvas frame and generation tokens must remain unchanged through capture. Other orientations/root-frame changes fail closed. Native validation must confirm this platform screenshot-coordinate contract.
