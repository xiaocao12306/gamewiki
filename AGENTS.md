# Repository Guidelines

## Project Structure & Module Organization
GameWiki ships as a Python/Qt desktop assistant. The runtime package lives in `src/game_wiki_tooltip/`, with `ai/` covering retrieval pipelines and vector stores, `core/` handling config and i18n utilities, `window_component/` providing the Qt overlay, and `assets/` bundling icons, HTML snippets, and packaged configs. `docs/` hosts contributor references (`BUILD.md`, `ARCHITECTURE.md`, `FAQ.md`, `QUICKSTART.md`). Knowledge bases and demo media reside in `data/`; keep large generated artifacts out of git unless curated for release. Build scripts such as `build_exe.py`, `download_vosk_models.py`, and installer specs sit at the repository root.

## Build, Test, and Development Commands
Run development from a virtual environment: `python -m venv .venv` then `.venv\Scripts\activate`. Install dependencies with `pip install -r requirements.txt`. Launch the app via `python -m src.game_wiki_tooltip` to verify desktop behavior. Use `python download_vosk_models.py` when voice recognition assets are required. Package a release with `python build_exe.py`; adjust `game_wiki_tooltip.spec` if you need custom PyInstaller flags.

## Coding Style & Naming Conventions
Target Python 3.8-3.11. Follow the existing 4-space indentation, snake_case for functions and modules, and PascalCase for Qt widget classes. Favor explicit type hints in new or refactored code, mirror logging patterns already present, and keep UI strings in the i18n layer. Before opening a PR, auto-format touched files with `black` (line width 88) and sort imports with `isort` or `ruff` if available; otherwise match the surrounding style.

## Testing Guidelines
There is no formal automated suite yet; add targeted unit or integration coverage alongside new features under `tests/` (create the folder as needed) using `pytest`. At minimum, exercise retrieval changes by running `python -m src.game_wiki_tooltip` and confirming overlay flows. When updating vector data, rerun the relevant scripts in `src/game_wiki_tooltip/ai/` (for example `build_vector_index.py`) and document outcomes in the PR.

## Commit & Pull Request Guidelines
Commits follow short, imperative subjects (`chat widget height fix`, `Update README.md`). Prefer concise scopes such as `ui: adjust tray icon tooltip` when multiple components change. Each PR should include a summary, clear testing notes (`python -m src.game_wiki_tooltip`, manual overlay check), linked issues, and screenshots or screencasts for UI updates. Mention any configuration prerequisites (for example `GEMINI_API_KEY`) and flag data migrations so reviewers can reproduce them.

Always Response with Chinese