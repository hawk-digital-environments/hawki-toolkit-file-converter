# v%%VERSION%%

### What's New

[//]: # (- The main new features and changes in this version.)
- The main content extraction engine was replaced with [kreuzberg](https://kreuzberg.dev/) which supports many file formats.
- If ocr extracted content than an `_ocr.md` file exists for an image based on its name. ( E.g.: ocr content for `foo.jpeg` can be found in `foo_ocr.md`).  
- The zip file contains a `metadata.md` file, which contains extracted metadata.
- Images are not nested in a subfolder for a specific document type (`images_pdf` or `images_word`) any more and now reside next to the main `content_markdown.md` file.
- Marker format changed from `"# Chunk 1-1\n\n## Page 1"` to `"\n\n--- Page {page_num} ---\n\n"` (kreuzberg's default).

### Quality of Life

[//]: # (- Improvements and enhancements that improve the user experience.)

### Bugfix

[//]: # (- List of bugs that have been fixed in this version.)

- For mixed pdf content (text&images) ocr content extraction now works.

### Deprecation

[//]: # (- List of features or functionalities that have been deprecated in this version.)
