## Project Overview

This project, "GameWikiTooltip," is an AI-powered in-game assistant for Windows. It provides a real-time overlay that can be activated with a hotkey (`Ctrl+Q`). This overlay offers two main features: a direct view of game wikis and an AI-powered chat assistant for answering questions about specific games.

The application is built with Python and uses PyQt6 for the user interface. It integrates WebView2 to render web-based content like wikis directly within the overlay. The AI functionality is powered by Google Gemini and a local Retrieval-Augmented Generation (RAG) system. This RAG system uses pre-built knowledge bases for several games (Helldivers 2, Elden Ring, Don't Starve Together, Civilization VI) to provide accurate, context-specific answers.

The assistant runs in the system tray and automatically detects when a supported game is being played. It is designed to be a seamless companion for gamers, eliminating the need to alt-tab out of the game to look up information.

## Key Technologies

*   **Backend:** Python 3.8+
*   **GUI:** PyQt6
*   **Web Rendering:** WebView2 (via `winrt-runtime` and `webview2-Microsoft.Web.WebView2.Core`)
*   **AI:** Google Gemini
*   **RAG/Search:**
    *   `faiss-cpu` for vector search (semantic)
    *   `bm25s` for keyword search
    *   `google-generativeai` for embedding and generation
*   **Windows Integration:** `pywin32` for global hotkey management and active window detection.
*   **Build Tool:** `PyInstaller`

## Building and Running

### Running from Source

1.  **Setup Environment:** Create and activate a Python virtual environment.
2.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
3.  **Set API Key (Optional):** For AI features, set your Google Gemini API key as an environment variable.
    ```bash
    # On Windows
    set GEMINI_API_KEY=your_key_here
    ```
4.  **Run the Application:**
    ```bash
    python -m src.game_wiki_tooltip
    ```

### Building the Executable

The project uses `PyInstaller` to create a standalone Windows executable.

1.  **Install Dependencies:** Ensure all dependencies from `requirements.txt` are installed.
2.  **Run the Build Script:**
    ```bash
    python build_exe.py
    ```
3.  **Output:** The final executable and its associated files will be located in the `GameWikiAssistant_Portable_onedir/` directory.

## Project Structure

*   `src/game_wiki_tooltip/`: The main application source code.
    *   `qt_app.py`: The main application entry point, handling the Qt application instance and system tray icon.
    *   `__main__.py`: Makes the `src.game_wiki_tooltip` package runnable.
    *   `window_component/`: Contains all UI-related components, such as the main overlay window (`unified_window.py`), chat view, and wiki view.
    *   `ai/`: Houses the entire RAG pipeline.
        *   `rag_query.py`: Orchestrates the query process from user input to final response.
        *   `hybrid_retriever.py`: Combines vector search and keyword search.
        *   `gemini_summarizer.py`: Generates the final answer using the Gemini API.
        *   `vectorstore/`: Contains the pre-built FAISS and BM25 indexes for each supported game.
    *   `core/`: Core utilities like configuration management (`config.py`) and internationalization (`i18n.py`).
    *   `assets/`: Static assets like icons, UI themes, and base configuration files (`games.json`).
*   `data/knowledge_chunk/`: The raw JSON data used to build the AI's knowledge base.
*   `docs/`: Detailed project documentation, including architecture, build instructions, and quick start guides.
*   `build_exe.py`: The script used to build the project into an executable using PyInstaller.
*   `requirements.txt`: A list of all Python dependencies for the project.
