# Third-party notices

bracket is licensed under Apache-2.0 (see `LICENSE`). The packaged app also contains, or downloads at the user's
request, the following. Each keeps its own license.

## Shipped inside the app

| Component | What it does here | License |
|---|---|---|
| [llama.cpp](https://github.com/ggml-org/llama.cpp) (`llama-server`) | runs the local model | MIT |
| [Python](https://www.python.org) | runtime | PSF License |
| [spaCy](https://spacy.io) and `en_core_web_sm` | sentence splitting, part of speech, named entities | MIT |
| [WordNet 3.0](https://wordnet.princeton.edu) (via NLTK) | the lexical tier's synonyms | WordNet License (BSD-style) |
| [NLTK](https://www.nltk.org) | WordNet access, stemming | Apache-2.0 |
| [lemminflect](https://github.com/bjascob/LemmInflect) | inflecting synonyms | MIT |
| [FastAPI](https://fastapi.tiangolo.com), [Starlette](https://www.starlette.io), [Uvicorn](https://www.uvicorn.org), [Pydantic](https://docs.pydantic.dev) | the local server | MIT / BSD-3-Clause |
| [HTTPX](https://www.python-httpx.org) | HTTP client | BSD-3-Clause |
| [Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python) | the optional Claude tier | MIT |
| [pypdf](https://github.com/py-pdf/pypdf) | reading PDF documents for the library | BSD-3-Clause |
| [platformdirs](https://github.com/tox-dev/platformdirs) | the per-user data folder | MIT |
| [pywebview](https://github.com/r0x0r/pywebview) (with PyObjC on macOS, pythonnet and Microsoft's WebView2 loader on Windows) | the app's own window | BSD-3-Clause; MIT; Microsoft WebView2 SDK licence |
| [Foundation Models SDK for Python](https://github.com/apple/python-apple-fm-sdk) (macOS build only) | Apple's on-device model | Apache-2.0 |
| Cormorant Garamond, DM Sans | typefaces | SIL Open Font License 1.1 (`frontend/fonts/OFL.txt`) |

The full dependency list with exact versions is `uv.lock`; each package's own license file is inside the app bundle
next to the package.

## The precedent library

`library/texts/` holds paragraphs of adopted, publicly released texts of NATO, the European Union (European Council),
the G7 and the G20, downloaded from the URLs in `library/sources.json` and quoted without alteration, with their
source. These are official statements published for public use; bracket's maintainers believe quoting them with
attribution is permitted, but this is not legal advice, and the terms of each publisher apply. To ship a build without
them, leave `library/texts/` empty.

## Downloaded at the user's request

Local models are downloaded from Hugging Face only when the user chooses one on the setup screen. All entries in
`backend/models.py` are Apache-2.0 (Google's Gemma 4 in Unsloth's GGUF conversions; Qwen 2.5 0.5B for automated tests),
pinned to a repository commit and checked against a SHA-256.
