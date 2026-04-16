# v%%VERSION%%

### What's New

[//]: # (- The main new features and changes in this version.)
- Workflows and jobs now run with [temporal](https://docs.temporal.io/)
- New asynchronous conversion pipeline alongside the existing synchronous `/extract` endpoint:
  - `POST /convert` starts a Temporal workflow and returns `{job_id, status, download_url}` immediately (`202 Accepted`). An optional `callback_url` form field may be supplied; the workflow POSTs `{job_id, status, download_url}` to it from a durable, retried Temporal activity when the conversion finishes.
  - `GET /download/{job_id}` streams the result zip. Idempotent within the TTL window — repeated downloads refresh the mtime and never delete the zip.
  - `GET /jobs` lists all workflows on the converter task queue (raw Temporal passthrough). Supports `?status=` filtering.
  - `GET /jobs/{job_id}` returns the merged Temporal describe + workflow status-query payload for a single job.
- Result zips are garbage-collected by a Temporal Schedule (`ttl-cleanup-zips`) that fires every 15 minutes and deletes job directories older than `ZIP_TTL_HOURS` (default 24). The schedule is registered idempotently by the FastAPI lifespan startup hook.
- `/extract` is unchanged and remains the synchronous API.

### Operational note

`ZIP_TTL_HOURS` is bounded by the temproal env `DEFAULT_NAMESPACE_RETENTION`. Temporal does not persist jobs beyond that time. The download and job-status endpoints query Temporal for the workflow record first; once retention purges the workflow, `/download/{job_id}` and `/jobs/{job_id}` return 404 — even if the zip is still on disk. Set `ZIP_TTL_HOURS <= DEFAULT_NAMESPACE_RETENTION` (both default to 24h) so the zip disappears before the workflow record does.

[//]: # (- The concept for the implementation can be found [here](https://github.com/hawk-digital-environments/hawk-ixdlab-docs/blob/main/hawki/RAG/file_extractor/readme.md))
- The main content extraction engine was replaced with [kreuzberg](https://kreuzberg.dev/) which supports more file formats.
- Images are not nested in a subfolder for a specific document type (`images_pdf` or `images_word`) any more. All extracted content conisdered assets now goes to the `assets` folder in zip.
- Extracted markdown content is chunked into the `chunks` folder. E.g. `chunks/00001.md` 
- If ocr extracted content than an `_ocr.md` file exists for an image based on its name. ( E.g.: `assets/image_1_ocr.webp`).
- All images are extraced as webp  
- The zip file contains a `meta.json` file, which contains extracted metadata.
- Marker format `"# Chunk 1-1\n\n## Page 1"` was replaced with a yaml header. For details [see](https://github.com/hawk-digital-environments/hawk-ixdlab-docs/blob/main/hawki/RAG/file_extractor/readme.md#chunks)
- documents with reflowed content mostly do not contain any page numbers in the header

### Quality of Life

[//]: # (- Improvements and enhancements that improve the user experience.)

### Bugfix

[//]: # (- List of bugs that have been fixed in this version.)

- For mixed pdf content (text&images) ocr content extraction now works.

### Deprecation

[//]: # (- List of features or functionalities that have been deprecated in this version.)
