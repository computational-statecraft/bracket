# [bracket]

**A drafting table for rooms that have to agree. People write; the machine only rewords.**

bracket is a full-screen editor for a group producing a short shared text: a communiqué, a statement of principles, a
joint strategy. One facilitator drives the keyboard, the room reads one projected screen and argues, and the draft is
worked through sentence by sentence until it is agreed. A model can suggest other words for the phrase under
discussion, stronger or weaker, plainer or more formal. It cannot add a claim, a name or a number. That rule is
enforced in code, not left to the prompt.

It runs entirely on one computer. An optional Claude tier can be switched on with an API key.

---

## Get started

No terminal, no Python, no separate installs.

**1. Download the app** for your computer from the
[latest release](https://github.com/computational-statecraft/bracket/releases/latest):

| Computer | File |
|---|---|
| Mac with Apple silicon (M1 or later) | [`bracket-macOS-arm64.dmg`](https://github.com/computational-statecraft/bracket/releases/latest/download/bracket-macOS-arm64.dmg) (about 175 MB) |
| Windows 10 or 11 (64-bit) | [`bracket-Windows-x64.zip`](https://github.com/computational-statecraft/bracket/releases/latest/download/bracket-Windows-x64.zip) (about 150 MB) |

Each release also carries `SHA256SUMS.txt` and a signed build attestation, so you can check that a download is the
file this repository's build made (see [Checking a download](#checking-a-download)).

**2. Open it.**

- **Mac:** open the `.dmg` and drag **bracket** to Applications. The first time, open it from Applications. If macOS says
  it cannot check the app for malicious software, click **Done**, then go to **System Settings → Privacy & Security**,
  scroll down to the message about bracket, click **Open Anyway** and confirm. You do this once. (See
  [Known limitations](#known-limitations-and-where-setup-may-not-be-smooth) for why.)
- **Windows:** right-click the `.zip`, choose **Extract All**, open the extracted `bracket` folder and double-click
  **bracket.exe**. If SmartScreen says "Windows protected your PC", click **More info → Run anyway**. You do this once.
- **Linux:** no packaged app; run from source (see [From source](#from-source)): it opens in your web browser.

bracket opens in its own window (on Linux, in your web browser). Closing the window, or **Quit** in Settings, stops
it. Press **F** on the setup screen, or ⌘⇧F / Ctrl+Shift+F while drafting, for full screen on the projector.

**3. Choose the local model.** The setup screen first lists what is already on your computer:

- the models in **Ollama**, if you use it and it is running;
- **Apple's on-device model** (Apple Intelligence), on a Mac with macOS 26 or later and Apple Intelligence turned on.
  If it is unavailable, the screen says why;
- models bracket has already downloaded.

Pick one and press **Use**. If you have none, choose a download: the screen recommends one for your computer's memory.
It downloads once from Hugging Face (no account needed) and then runs offline; meanwhile you can name the session and
paste your draft. When the **Local model** row says *Ready*, press **Begin**. **Change model** switches later.

That's it. To use Claude as well, paste an Anthropic API key into the **Claude** row (see [Claude](#claude-optional)).

### Which model?

| Your computer's memory | Recommended | Download | Notes |
|---|---|---|---|
| 8 GB | Gemma 4 E2B | 3.1 GB | fastest, lightest |
| 16 GB | Gemma 4 E4B | 5.0 GB | fast, better wording |
| 16 GB or more | Gemma 4 12B | 7.1 GB | dense: stronger wording, slower than E4B |
| 32 GB or more | Gemma 4 26B A4B | 16.9 GB | best wording; mixture of experts, so quick for its size |

All are Google's Gemma 4 (Apache-2.0), 4-bit quantised GGUF files, pinned to an exact file and checked against its
SHA-256 after download. You can switch models later in **Settings**, or point bracket at your own GGUF file. The
memory thresholds are rules of thumb, not benchmarks: speed depends on the machine, and on Windows and Linux the
built-in engine runs on the CPU (see [Known limitations](#known-limitations-and-where-setup-may-not-be-smooth)).

---

## In the room

Put bracket's window on the projector and press **F** for full screen. The setup screen takes you through four steps:
**the draft** (paste it, open a file, or drop one on the box), **the local model**, **Claude** (optional) and **agreed
language** (optional). Then press **Begin** (⌘↵ / Ctrl+↵). Structure survives: headings, bold lead-ins
(`**Purpose:** …`), numbered and bulleted items. **System · Light · Dark** at the foot of the setup screen, or ⌥T at any
time, switches between a dark screen (best on most projectors) and a light one.

The sentence being worked on is white at reading height; the rest of the text is grey around it.
**Double-click a word or select a phrase** and the proposals open beneath it:

- **Agreed language** at the top, if you have added documents: up to three sentences from texts your group has
  already adopted, quoted exactly with their source and paragraph, aligned to your selection. Use one (↵) or keep it
  beside your wording in brackets (⇧↵).
- **The local model's proposals** in a grid, at the current **strength** (←→), **length** (↑↓) and **register**
  (`R`: plain, institutional, formal diplomatic). Strength runs on one scale, *weaker · weak · same · strong ·
  stronger*, counted from the current wording. On a verb that carries force, each step aims the models at the
  next rung of a ladder drawn from UN practice (*note → acknowledge → recognize → reaffirm*,
  *invite → encourage → urge → call upon → request → require*, *may → should → shall → must*).
- **`C`** adds six proposals from Claude (if switched on); `C` again replaces all nine with fresh ones.
- Pick with **1–9**, accept with **↵**, or **⇧↵** to keep the proposal *alongside* the current wording as a bracket.

**Brackets** keep unsettled wording in the text, as negotiators do: `[review / reassess]`. They are tinted gold, the
margin counts them, and **a sentence with an open bracket cannot be marked agreed.** Double-click a bracket to settle it
(↑↓ choose, ↵ settle), add an alternative (`B`) or drop one (`X`).

**Agreement is provisional.** ⇧↵ marks a sentence agreed; editing it returns it to draft. Nothing is agreed until
everything is agreed, and the bar along the bottom shows how much is.

| Key (Mac / Windows & Linux) | Does |
|---|---|
| double-click, or select | proposals and agreed language for that word or phrase |
| ⌘↵ / Ctrl+↵ | rewrite the whole sentence (same grid) |
| ⌥B / Alt+B | bracket the word at the caret, or open the bracket it is in |
| ⌥ / Alt + hover | instant synonyms for the word under the pointer |
| ⇧↵ / Shift+↵ | toggle agreed |
| ⌥O / Alt+O | mark open (contested) |
| ⌥D / Alt+D | record a dissent: `Name — one line` |
| ⌥H / Alt+H | the sentence's history |
| ⌥↑↓ / Alt+↑↓ | move between sentences |
| ⌘Z / Ctrl+Z, ⌘⇧Z / Ctrl+Shift+Z | undo / redo (typing, proposals, splits, joins, states) |
| ⌥E / Alt+E | save the statement (`.docx`), the statement with its history (`.md`) and the session (`.json`) to Downloads |
| ⌥T / Alt+T | light or dark |
| ⌥Q / Alt+Q | end the session (asks first, saves the record) |

The draft is saved continuously. If the computer restarts, open bracket again and press **Resume**.

## Opening and saving

- **Open a draft** from the setup screen (**Open a file…**, or drop it on the draft box): Word (`.docx`), Markdown or
  text, PDF, or a web page. Headings, numbered and bulleted items, and bold lead-ins are kept; a Word document's title
  becomes the session's name. Older Word files (`.doc`) need saving as `.docx` first.
- **Save** with ⌥E at any time, and automatically when the session ends (⌥Q). Three files go to Downloads:
  - the statement as a **Word document** (`.docx`), with its structure and any brackets still open, to send on;
  - the statement with **each sentence's history and the dissents** (`.md`);
  - the **session** (`.json`): the draft exactly as it stands, with every state, version, bracket and dissent, and the
    full record of what was proposed, accepted and refused. Open it again from the setup screen to continue.

## What the machine may and may not do

Every proposal, from any tier, passes a validator (`backend/validate.py`) before the room sees it:

- **Dropped:** a proposal that introduces a named entity (a country, organization or person) not already in the
  sentence; a "replacement" for a phrase that is really a whole rewritten sentence.
- **Flagged for the room** (▲): a changed number, a changed modal (*should* → *must*), added or removed negation, a
  large jump in length. These are left to people to accept or refuse.
- **Never generated:** agreed language. Precedents are retrieved and quoted verbatim, with their source, never
  paraphrased by a model.
- **Untouched:** bracketed text. The models are told to leave it exactly as it is.

The models get one short instruction: keep the meaning, subject and polarity; add no claims, facts, names, numbers or
commitments. `uv run python -m backend.show_prompts` prints exactly what they are sent.

## The record

Everything that happens is appended to a local SQLite log: every proposal shown, accepted and rejected (including
those the validator dropped, with the model's raw output), every edit, bracket, precedent, state change and dissent.
⌥E saves the statement with each sentence's history and the dissents as Markdown, and the session with the full log as
JSON (see [Opening and saving](#opening-and-saving)). The log
records what was offered and refused as well as what was chosen, so a session can be studied afterwards. Note that the
Markdown export shows each sentence's versions but not which edits came from a model; the JSON log has that.

## Privacy: what stays on this computer

- **Everything, by default.** The local model, the lexicon, your agreed-language documents and the log all run and live on
  your machine. bracket listens only on `127.0.0.1`, and rejects requests that are not addressed to this machine or
  that come from another website.
- **Only with Claude switched on**, and only when the facilitator presses `C` or rewrites a whole sentence: the
  sentence being worked on (and, for a rewrite, its neighbours) is sent to the Anthropic API under your key. Nothing
  else is sent. `Fetch Claude ahead` in Settings trades this for speed by asking for every opened word; it is off by default.
- **Network use otherwise:** downloading a model (Hugging Face), only when you choose one. Nothing else, and no
  telemetry.

Where things are kept:

| | macOS | Windows | Linux |
|---|---|---|---|
| Settings, models, logs | `~/Library/Application Support/bracket` | `%LOCALAPPDATA%\bracket` | `~/.local/share/bracket` |

`settings.json` there holds the API key in plain text, readable only by your user account. To remove everything,
quit bracket and delete that folder.

## Claude (optional)

Paste an Anthropic API key (from [console.anthropic.com](https://console.anthropic.com)) into the **Claude** row and
press **Save**. The setup screen tests it with a real request. In **Settings** you can choose the model (default
`claude-sonnet-5-5`; `claude-haiku-5-5` is faster), remove the key, or turn the tier off entirely. Organizations that
reach Claude through their own gateway in front of AWS Bedrock can set **Route**, **Gateway base URL** and the key
header there.

## Agreed language

bracket can show, above the proposals, sentences from texts your group has already adopted: earlier declarations,
conclusions, communiqués. They are quoted exactly, cited by body, title, year and paragraph, and never rewritten by a
model. bracket ships with none: add your own on the setup screen (**Agreed language → Add a document**; PDF, Word, web
page, text or Markdown). They are kept in the data folder's `library/`.

Search is lexical (SQLite full-text search with stemming), so it finds shared wording, not shared meaning: a precedent
that says the same thing in other words will not show.

## Programmable

Everything the setup screen does is available without it.

**Settings** come from three layers, highest first: an environment variable, then `settings.json` in the data folder,
then the default. A setting fixed by an environment variable shows as locked in Settings.

| Setting | Environment variable | Default |
|---|---|---|
| Local engine: `builtin`, `ollama`, `apple`, `openai` (any OpenAI-compatible server), `off` | `BRACKET_LOCAL_ENGINE` | chosen on the setup screen |
| Local model (catalog id for `builtin`; the server's model name otherwise) | `BRACKET_LOCAL_MODEL` | the recommended download |
| Your own GGUF file for `builtin` | `BRACKET_LOCAL_MODEL_PATH` | |
| Local server address (`ollama` / `openai`) | `BRACKET_LOCAL_URL` | `http://127.0.0.1:11434` for Ollama |
| Seconds before a local answer is abandoned | `BRACKET_LOCAL_TIMEOUT` | `8` |
| Claude route: `anthropic`, `bedrock-gateway`, `off` | `BRACKET_CLOUD_API` | `anthropic` |
| API key | `BRACKET_CLOUD_KEY` (or `ANTHROPIC_API_KEY`) | |
| Claude model | `BRACKET_CLOUD_MODEL` | `claude-sonnet-5-5` |
| Proxy or gateway URL; key header; bearer auth | `BRACKET_CLOUD_BASE_URL`, `BRACKET_CLOUD_KEY_HEADER`, `BRACKET_CLOUD_AUTH` | |
| Fetch Claude ahead | `BRACKET_CLAUDE_PREFETCH` | off |
| Session title; label under the mark; session name (`new` forces a fresh one) | `BRACKET_TITLE`, `BRACKET_ORG`, `BRACKET_SESSION` | |
| Data folder | `BRACKET_DATA` | per-user folder above |

**HTTP API.** The page is a client of a local JSON API: status, settings, model downloads, proposals (streamed as
server-sent events), precedents, the log and exports. See [`docs/API.md`](docs/API.md); a live schema is at
`http://127.0.0.1:8765/docs` while bracket runs.

**Command line** (the packaged app's executable, or `uv run python launcher.py` from source):
`--headless` (serve without window or browser), `--browser` (use the browser instead of the app window), `--port N`,
`--data DIR`, `--doctor` (check every tier with real calls), `--version`.

**Editable parts.** The strength ladders are a plain list in `backend/lexicon.py` (`LADDERS`); the model catalog is
`backend/models.py`; the prompt is `backend/prompts.py`; the guard is `backend/validate.py`.

## From source

For development. You need [uv](https://docs.astral.sh/uv/getting-started/installation/), which installs the right
Python and the exact locked dependencies.

```bash
git clone https://github.com/computational-statecraft/bracket.git
```

```bash
cd bracket && uv sync
```

```bash
uv run python launcher.py
```

From source, the built-in engine needs llama.cpp's `llama-server`: install it (for example `brew install llama.cpp`),
point `BRACKET_LLAMA_SERVER` at it, or choose **Ollama** in Settings. WordNet downloads into the data folder on first
start.

| Task | Command |
|---|---|
| tests | `uv run pytest -q` |
| check the setup with real calls | `uv run python -m backend.doctor` |
| local model vs Claude, side by side | `uv run python -m backend.compare` |
| what the models are sent | `uv run python -m backend.show_prompts` |
| agreed language from the command line | `uv run python -m backend.library_cli add \| fetch \| list \| search` |
| build the app | `uv sync --group build && uv run pyinstaller packaging/bracket.spec` |

**Releases** are built by `.github/workflows/build.yml`. A push to a working branch runs the unit tests on Linux only.
A push to `main`, a pull request, a tag or a manual run (**Actions → build → Run workflow**) runs everything: tests on
macOS, Windows and Linux; the Mac and Windows apps built with llama.cpp bundled; and each build smoke-tested as a new
user would meet it (an empty data folder, a model downloaded through the app, real proposals from the built-in engine,
opening a Word draft, saving and reopening a session, adding agreed language, the app's own window). A manual run with
**Keep the built apps** ticked keeps the two apps for 3 days, for trying them out; pushing a tag `v*` publishes them
as a GitHub Release. The limits are there because private repositories have a small allowance of Actions minutes and
storage (the three apps are about 0.5 GB per run).

**The website** is `site/` (plain HTML, CSS and JavaScript; no build step). `.github/workflows/pages.yml` publishes it
to GitHub Pages when it changes on `main`; turn Pages on once under **Settings → Pages → Source: GitHub Actions**.
Preview it locally with `python3 -m http.server -d site`.

```
backend/    app.py (HTTP API) · config.py (settings) · engine.py (llama.cpp) · models.py (catalog, downloads)
            local_llm.py · cloud_llm.py · prompts.py · validate.py (the guard) · lexicon.py (WordNet, ladders)
            library.py · library_cli.py (agreed language) · docfiles.py (open and save Word, sessions) · nlp.py · draft.py
            store.py (the log) · doctor.py · compare.py
frontend/   index.html (setup and the live editor) · fonts/
site/       the project website                 launcher.py the desktop entry point
packaging/  PyInstaller spec, icon, smoke test
```

---

## Origins and precedent

bracket takes its working objects from the practice of multilateral negotiation and its main constraint from recent
human–computer interaction research. It sits deliberately apart from the systems, many from large AI labs, in which a
model writes the shared text.

**Negotiating text as a practice.** Diplomats have long drafted in the open with a small vocabulary of devices:
square brackets for wording not yet agreed, "agreed language" carried over verbatim from earlier adopted texts, and a
single rolling text that every party edits. Riles's ethnography of UN conference drafting treats brackets as the
central aesthetic and technical device of that work (Riles 1998, 2000). Fisher's *single negotiating text*, used by the
United States at Camp David in 1978, replaced competing drafts with one text revised in rounds (Fisher & Ury 1981;
Raiffa 1982). Depledge (2005) shows how bracketed drafts structure, and can stall, the climate negotiations, and
negotiators' handbooks describe the work as clearing brackets without reopening text already agreed. Most directly,
Adler-Nissen and Drieschova's study of EU negotiators (2019) shows that word-processor features such as track changes,
shared screens and copy-pasted precedent shape how negotiations unfold, and warns that these affordances can produce
loss of control and texts nobody quite intended. bracket is best read as a further affordance in that line: the
bracket, the agreed language and the one text become software objects with rules attached. A sentence holding a
bracket cannot be marked agreed, precedent is quoted rather than generated, and one person holds the keyboard. Whether
that answers the loss-of-control problem is a hypothesis the tool is built to test, not a result.

**Why the machine is limited to rewording.** Controlled studies find that a writing assistant with a point of view
shifts what people write and, afterwards, what they say they believe, mostly without their noticing (Jakesch et al.
2023; Williams-Ceci et al. 2025†), and that suggestions pull prose toward the model's default style (Agarwal, Naaman &
Vashistha 2025). In simulated crises, language models tend toward escalation (Rivera et al. 2024), and in wargames
they act more aggressively than expert human players (Lamparth et al. 2024). For a room of principals negotiating substance, those
are reasons to keep the model away from positions. bracket confines it to what it is good at and a room is slow at,
finding the next word, and makes the boundary mechanical: the validator drops proposals that add entities and flags
changes to modality, negation and number. The strength ladders follow the operative-verb conventions of UN resolutions
and similar practice; there is no official ranked list, and these are the project's own.

**AI-assisted deliberation, and where bracket differs.** The most prominent systems for reaching agreement with
language models come from large labs and technology companies, and most let the model write. DeepMind's work on
consensus statements, from fine-tuning models to find agreement among people with diverse preferences (Bakker et al.
2022) to the *Habermas Machine* (Tessler et al. 2024), has a model draft group statements that participants then rank;
in the 2024 study they preferred them to statements written by human mediators. Meta's CICERO negotiated in natural
language at human level in the game *Diplomacy* (Meta FAIR 2022). Anthropic's Collective Constitutional AI gathered
principles from a representative public to shape a model's behaviour (Huang et al. 2024). Microsoft's Teams Facilitator
agent takes notes and summarises meetings for the whole group. Open civic tools such as Polis, used in
Taiwan's vTaiwan process, cluster and select among statements that participants write. These systems answer a
different question, usually how to aggregate the views of many people at scale, and in most of them the model (or the
selection algorithm) produces the shared text. bracket answers a narrower one: how a small room of decision-makers can
use a model without handing it the pen. In the human–computer interaction tradition its nearest relatives are logged
co-writing environments built for study (CoAuthor: Lee, Liang & Yang 2022) and Ink & Switch's research on versioned
collaborative writing (Upwelling, 2023; Patchwork, 2024), which argues that AI edits, like a collaborator's, should be
staged as changes for others to review rather than applied silently.

**What is and is not new here.** None of the components is new: versioned one-text drafting is a 1970s procedure, and
live editors, model rewording, local inference and full-text search are off the shelf. What bracket adds is the
combination and the constraint: brackets that block agreement, verbatim precedent inside a live drafting surface, a
walkable wording-strength control, and a reword-only rule enforced in code, with a log of what was offered and refused.
It makes no claim that a model improves negotiated outcomes. That is an open question, and the log exists to help
answer it.

### References

Works marked † were identified in a 2026 literature scan and have not been checked against the published text by the
maintainers; verify them before citing.

- Adler-Nissen, R., & Drieschova, A. (2019). Track-change diplomacy: Technology, affordances, and the practice of
  international negotiations. *International Studies Quarterly*, 63(3).
- Agarwal, D., Naaman, M., & Vashistha, A. (2025). AI suggestions homogenize writing toward Western styles and diminish
  cultural nuances. *Proceedings of CHI 2025*.
- Bakker, M., et al. (2022). Fine-tuning language models to find agreement among humans with diverse preferences.
  *Advances in Neural Information Processing Systems 35*.
- Depledge, J. (2005). *The Organization of Global Negotiations: Constructing the Climate Change Regime*. Earthscan.
- Fisher, R., & Ury, W. (1981). *Getting to Yes: Negotiating Agreement Without Giving In*. Houghton Mifflin.
- Huang, S., et al. (2024). Collective Constitutional AI: Aligning a language model with public input. *Proceedings of
  FAccT 2024*.
- Jakesch, M., Bhat, A., Buschek, D., Zalmanson, L., & Naaman, M. (2023). Co-writing with opinionated language models
  affects users' views. *Proceedings of CHI 2023*.
- Lamparth, M., et al. (2024). Human vs. machine: Behavioral differences between expert humans and language models in
  wargame simulations. arXiv:2403.03407.
- Lee, M., Liang, P., & Yang, Q. (2022). CoAuthor: Designing a human–AI collaborative writing dataset for exploring
  language model capabilities. *Proceedings of CHI 2022*.
- Meta Fundamental AI Research Diplomacy Team (FAIR) et al. (2022). Human-level play in the game of *Diplomacy* by
  combining language models with strategic reasoning. *Science*, 378.
- Raiffa, H. (1982). *The Art and Science of Negotiation*. Harvard University Press.
- Riles, A. (1998). Infinity within the brackets. *American Ethnologist*, 25(3).
- Riles, A. (2000). *The Network Inside Out*. University of Michigan Press.
- Rivera, J.-P., et al. (2024). Escalation risks from language models in military and diplomatic decision-making.
  *Proceedings of FAccT 2024*.
- Tessler, M. H., et al. (2024). AI can help humans find common ground in democratic deliberation. *Science*, 386.
- Ink & Switch (2023). *Upwelling: Combining real-time collaboration with version control for writers*.
- Ink & Switch (2024). *Patchwork: Version control for everything* (lab notebook).
- † Williams-Ceci, S., et al. (2025). Biased AI writing assistants shift users' attitudes on societal issues.

---

## Known limitations, and where setup may not be smooth

- **Unsigned apps.** The builds are not yet signed with an Apple Developer ID or a Windows code-signing certificate,
  so macOS Gatekeeper and Windows SmartScreen warn on first open (the one-time steps are above). Signing needs a paid
  Apple Developer account and a Windows certificate; the build workflow is the place to add them.
- **Platforms built.** Apple-silicon Macs and 64-bit Windows. Linux runs from source; Intel Macs and ARM Windows are
  not built (llama.cpp publishes binaries for them, so they can be added to the build matrix).
- **No GPU on Windows and Linux.** The bundled engine there is llama.cpp's CPU build, which works everywhere but is
  slower; on those machines prefer E2B or E4B. Macs use the GPU (Metal). For a GPU elsewhere, run Ollama or LM Studio
  and choose it in Settings.
- **Apple's on-device model** is untested in real use: it needs Apple Intelligence hardware, which automated builds lack.
  Apple's content filter, even in its rewriting mode, may decline some security or diplomatic wording; the room then
  sees that it declined, and another model can be chosen.
- **Model downloads are large** (3–17 GB) and need disk space and a decent connection. They resume if interrupted.
  Networks that block Hugging Face will need the model copied in by hand (Settings → *Your own GGUF file*).
- **Speed has not been benchmarked across machines.** The model recommendations are memory-based rules of thumb.
- **Alt shortcuts on Windows.** bracket takes Alt+letter keys for itself; some browsers or keyboard layouts may
  intercept a few of them.
- **Name.** Other products use "bracket" or "brackets"; search for "computational-statecraft/bracket".

## Checking a download

Because the apps are not yet code-signed, each release carries two ways to check that a file is the one this
repository's build workflow made, from a tagged commit, and has not been swapped or altered since:

- **Checksums.** `SHA256SUMS.txt` on the release lists each file's SHA-256. In the folder holding both files:

  ```bash
  shasum -a 256 -c SHA256SUMS.txt --ignore-missing
  ```

  On Windows (PowerShell), compare `Get-FileHash bracket-Windows-x64.zip` with the line in `SHA256SUMS.txt`.
  A checksum from the same page catches a damaged or swapped mirror copy, not a compromised release page; the
  attestation below covers that.
- **Build attestation.** Each file is attested with GitHub's signed build provenance, which names the workflow, the
  commit and the repository that built it. With the [GitHub CLI](https://cli.github.com):

  ```bash
  gh attestation verify bracket-macOS-arm64.dmg --repo computational-statecraft/bracket
  ```

## Licence

Apache-2.0 (`LICENSE`). Third-party components and their licences are listed in `THIRD_PARTY_NOTICES.md`.
bracket is developed by the Project on Computational Statecraft.
