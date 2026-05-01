# CopyDesk - AI-Powered Content Evaluation System

A hierarchical evaluation system for checking government content compliance with style guides, brand tone, and factual accuracy. Features a modern Material Design web interface for real-time content evaluation with live progress tracking and formatted reports.

## Overview

This framework evaluates content across three key dimensions:

1. **Style Guide Compliance** - Checks against the Australian Government Style Manual
2. **Brand Tone** - Ensures alignment with organisational voice and strategy documents  
3. **Fact Checking** - Validates service information and URLs

## Architecture

The system uses a hierarchical evaluation structure inspired by editorial workflows:

- **Junior Evaluators**: Check content against single reference sources (e.g., one style guide page)
- **Senior Evaluators**: Aggregate multiple junior reports for section-level insights
- **Editor**: Synthesizes all senior reports into executive recommendations

```
Content → Junior Evaluators (parallel) → Senior Evaluators → Editor → Final Report
             ↓                              ↓                    ↓
        Page-level issues            Section patterns      Executive summary
```

## Key Features

- **Real-time web scraping** of style guide pages (no manual rule maintenance)
- **Parallel evaluation** with configurable concurrency limits
- **Intelligent caching** to reduce API calls and improve performance
- **Multiple LLM support** (OpenAI, Google AI, Anthropic)
- **Detailed reporting** with severity levels and actionable recommendations

## Quick Start

### Installation with Poetry

```bash
# Install Poetry if you haven't already
curl -sSL https://install.python-poetry.org | python3 -

# Clone the repository (if you haven't already)
git clone <repository-url>
cd CopyDesk

# Install dependencies
poetry install

# Set up API keys (choose one or both)
export GOOGLE_API_KEY="your-google-ai-studio-key"
export OPENAI_API_KEY="your-openai-key"
```

### Web Interface (Recommended)

#### Option 1: Using the startup script (Easiest)

```bash
# Linux/Mac
./run.sh

# Windows
run.bat
```

#### Option 2: Using Poetry directly

```bash
# Start the web application
poetry run python app.py

# Or use the Poetry script command
poetry run copydesk-web
```

#### Option 3: Activate Poetry shell

```bash
# Activate the Poetry virtual environment
poetry shell

# Run the application directly
python app.py
```

After starting, open your browser and navigate to: **http://localhost:5000**

### Command Line Interface

```bash
# Run a test evaluation
poetry run python test.py

# Run the full framework test
poetry run python test_framework.py
```

### Production Deployment

For production environments, use a proper WSGI server:

```bash
# Install production dependencies
poetry install --with production

# Run with gunicorn (Linux/Mac)
./run_production.sh

# Or manually with custom settings
poetry run gunicorn --worker-class eventlet --workers 4 --bind 0.0.0.0:8000 app:app
```

## Web Interface Features

The CopyDesk web interface provides:

- **Material Design UI**: Clean, modern interface following Google's Material Design principles
- **Real-time Progress Tracking**: Live updates via WebSocket showing:
  - Section-by-section evaluation progress
  - Individual page evaluation status
  - Overall completion percentage
- **Interactive Text Input**: Large text area with word/character counting
- **Customisable Evaluation**: Select which style guide sections to check
- **Visual Results Dashboard**:
  - Circular compliance score chart
  - Issue severity breakdown
  - Color-coded recommendations
- **Formatted Reports**:
  - Executive summary with top recommendations
  - Detailed issue listing grouped by section
  - Full markdown report with export options
- **Evaluation History**: Track and review past evaluations

## Project Structure

```
copydesk/
├── app.py                     # Flask web application server
├── templates/
│   └── index.html            # Material Design web interface
├── static/
│   ├── css/
│   │   └── style.css        # Custom styles
│   └── js/
│       └── app.js           # Frontend JavaScript with WebSocket
├── evaluators/
│   ├── base.py              # Base evaluator classes
│   ├── style_guide/         # Style guide compliance checking
│   │   ├── page_evaluator.py  # Evaluates against single pages
│   │   ├── section_lead.py    # Aggregates page reports
│   │   └── editor.py          # Final synthesis
│   ├── brand_tone/          # Brand voice alignment (future)
│   └── fact_check/          # Fact checking system
├── utils/
│   ├── document_fetcher.py  # Web scraping utilities
│   ├── mcp_client.py       # MCP integration client
│   └── rate_limiter.py    # API rate limiting
├── config/
│   └── evaluation_config.yaml # Configuration settings
├── requirements.txt         # Python dependencies
└── test_*.py               # Various test scripts
```

## Configuration

Edit `config/evaluation_config.yaml` to customise:

- **Model selection** - Choose between Google (Gemma), OpenAI, or Anthropic models
- **Concurrency limits** - Control parallel evaluation rate
- **Cache settings** - Configure result caching
- **Report verbosity** - Adjust detail levels

### Example Configuration

```yaml
models:
  junior:
    provider: "google"
    model: "gemma-3-27b-it"  # Free via Google AI Studio
    temperature: 0.3
  senior:
    provider: "openai"
    model: "gpt-4o-mini"     # Cost-effective aggregation
  editor:
    provider: "openai"  
    model: "gpt-4o"          # Best for final synthesis

performance:
  max_concurrent_juniors: 10
  rate_limit:
    requests_per_minute: 60
```

## Usage Examples

### Web Interface

1. Start the web server with `poetry run python app.py`
2. Open http://localhost:5000 in your browser
3. Enter or paste your text in the input area
4. Select which style guide sections to evaluate
5. Click "Start Evaluation" to begin
6. Watch real-time progress as each section is analysed
7. View the comprehensive report with scores and recommendations

### Python API

```python
from evaluators.style_guide.page_evaluator import StyleGuidePageEvaluator

# Create evaluator
evaluator = StyleGuidePageEvaluator("page_eval_1", config)

# Evaluate content
report = await evaluator.evaluate(
    content="Your text to evaluate",
    context={"source": "https://www.stylemanual.gov.au/writing-style/plain-language"}
)

# Access results
print(f"Score: {report.score:.1%}")
for issue in report.issues:
    print(f"- {issue.severity.name}: {issue.description}")
```

### REST API

```bash
# Start an evaluation
curl -X POST http://localhost:5000/api/evaluate \
  -H "Content-Type: application/json" \
  -d '{"text": "Your content here", "options": {"sections": ["Grammar and punctuation"]}}'

# Get evaluation status
curl http://localhost:5000/api/evaluation/{evaluation_id}

# List all evaluations
curl http://localhost:5000/api/evaluations
```

## Development Status

### Implemented ✅
- Core evaluation framework with hierarchical structure
- Style guide page fetching and evaluation
- Material Design web interface with real-time updates
- WebSocket integration for live progress tracking
- REST API for programmatic access
- Visual reporting dashboard with charts
- Evaluation history tracking
- Caching and performance optimization

### In Progress 🚧
- Full style guide section aggregation
- Report generation and formatting
- MCP server integration

### Planned 📋
- Brand tone evaluation using strategy documents
- Fact checking with service registry
- Rules as Code integration
- Fine-tuned model evaluation

## Testing

Run the test scripts to verify functionality:

```bash
# Test basic Gemma 3 integration
poetry run python test.py

# Test the evaluation framework
poetry run python test_framework.py

# Test web scraping functionality
poetry run python test_scraping.py

# Test word substitution table usage
poetry run python test_word_table.py

## MCP Integration

This app can query the local MCP server to use your Typesense-backed fragments as ground-truth for fact checking.

- MCP HTTP bridge default: `http://localhost:8081` (set `MCP_SERVER_URL` to override)
- Endpoints used: `POST /search`, `POST /analyze-combinations`, `POST /rank-content`

Quick demo:

1. Ensure the MCP server is running (from repo root):
   - `node mcp-server/index.js` (or via docker-compose)
2. Ensure Typesense has the `content_fragments` collection populated.
3. Run the fact-checker:

```bash
export OPENAI_API_KEY=...   # used for structured LLM parsing
# export MCP_SERVER_URL=http://127.0.0.1:8081  # optional override
python -m copydesk.test_facts "Write your content here about a gov service"
```

Where it lives:
- `utils/mcp_client.py` — async client for the MCP HTTP bridge
- `evaluators/fact_check/fragment_facts.py` — fact-check evaluator using MCP fragments

Config knobs:
- `config/evaluation_config.yaml`:
  - `mcp_server.base_url`: default MCP URL
  - `fact_check_fragments.per_page`: number of fragments to include
```

## Environment Setup

### Using .env file (Recommended)

1. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` and add your API keys:
   ```bash
   # Edit with your preferred editor
   nano .env
   # or
   code .env
   ```

3. The application will automatically load these on startup

### API Keys

The framework supports multiple LLM providers:

1. **Google AI Studio** (Recommended for testing - free tier available)
   - Get key from: https://aistudio.google.com/apikey
   - Models: Gemma 3 27B-IT
   - Set as: `GOOGLE_API_KEY`

2. **OpenAI** (Optional - for senior/editor roles)
   - Get key from: https://platform.openai.com/api-keys
   - Models: GPT-4o, GPT-4o-mini
   - Set as: `OPENAI_API_KEY`

3. **Anthropic** (Optional)
   - Get key from: https://console.anthropic.com/
   - Models: Claude 3 family
   - Set as: `ANTHROPIC_API_KEY`

## Contributing

This is an experimental framework for evaluating government content. Contributions welcome!

Key areas for contribution:
- Additional evaluator types
- Report formatting improvements
- Performance optimizations
- Test coverage

## License

[To be determined]

## Acknowledgments

Built to support Australian Government digital service delivery, referencing:
- [Australian Government Style Manual](https://www.stylemanual.gov.au)
- Services Australia strategy documents
- Digital service s
