# Local AI Setup for MPWRD DSS Assistant

The dashboard supports an optional free local AI layer through Ollama. The local
model does not replace the deterministic DSS query engine. It only improves the
wording and operational interpretation of grounded dashboard results.

## Recommended Model

- Runtime: Ollama
- Model: `llama3.2:3b`

## Setup

1. Install Ollama from `https://ollama.com/download`.
2. Pull the model:

```powershell
ollama pull llama3.2:3b
```

3. Start or confirm Ollama is running:

```powershell
ollama serve
```

4. Configure Streamlit secrets:

```toml
local_ai_enabled = "true"
local_ai_provider = "ollama"
ollama_base_url = "http://127.0.0.1:11434"
ollama_model = "llama3.2:3b"
```

For Streamlit Cloud, local Ollama on `127.0.0.1` will not be available unless a
separate hosted Ollama-compatible endpoint is provided.
