# MORICE 0.9.4 — online places and prompt-only images

Spatial now searches online for named cities, states, countries and smaller places. The existing kernel owns the new network capability and its permissions, deadline and verification. Photon/OpenStreetMap results have source links and location types, queries are cached for one day, and failed online requests can fall back to the installed GeoNames city data. The GUI stays responsive while a lookup runs.

Questions such as `show mumbai and pakistan how far?` no longer include `how far` in the destination. `Gujrat` offers the Pakistani city and the Indian state `Gujarat` for explicit selection. State/country distances are labelled as measurements between representative coordinates; they are not road routes or nearest-border distances.

Overlapping Spatial commands report busy immediately. Generic file-location requests retain the existing chat/file route. Lookup timeouts allow healthy slower provider responses while preserving deadlines, caching and offline fallback.

Media defaults to prompt-only image generation with no reference or mask. Optional edit controls are collapsed. Generate checks a discovered model on demand, explains missing models/dependencies/resources visibly, and prevents duplicate preparation clicks. Editing/inpainting retain their actual image/mask requirements. Existing models, resource leases, permission handling and artifact verification remain in place.

See the [guide and constraints](spatial-media-0.9.4.md) and [validation](spatial-media-validation-0.9.4.md). Compatible local model weights and adequate RAM/VRAM are still required. No new model download or physical-device certification is claimed.
