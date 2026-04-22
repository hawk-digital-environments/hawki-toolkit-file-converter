# v%%VERSION%%

### What's New

[//]: # (- The main new features and changes in this version.)
- The concept for the implementation can be found [here](https://github.com/hawk-digital-environments/hawk-ixdlab-docs/blob/main/hawki/RAG/file_extractor/readme.md)
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
