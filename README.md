# Speech Evaluator Framework

A hierarchical evaluation system for checking government content compliance with style guides, brand tone, and factual accuracy. Uses a multi-tiered approach with specialized evaluators working together to provide comprehensive content assessment.

## Overview

This framework evaluates content across three key dimensions:

1. **Style Guide Compliance** - Checks against the Australian Government Style Manual
2. **Brand Tone** - Ensures alignment with organizational voice and strategy documents  
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

```bash
# Install dependencies
pip install -r requirements.txt

# Set up API keys
export GOOGLE_API_KEY="your-google-ai-studio-key"
export OPENAI_API_KEY="your-openai-key"  # Optional

# Run a test evaluation
python test.py

# Run the full framework test
python test_framework.py
```

## Project Structure

```
speech-evaluator/
├── evaluators/
│   ├── base.py                 # Base evaluator classes
│   ├── style_guide/           # Style guide compliance checking
│   │   ├── page_evaluator.py  # Evaluates against single pages
│   │   ├── section_lead.py    # Aggregates page reports
│   │   └── editor.py          # Final synthesis
│   ├── brand_tone/            # Brand voice alignment (future)
│   └── fact_check/            # Fact checking system (future)
├── utils/
│   └── document_fetcher.py    # Web scraping utilities
├── config/
│   └── evaluation_config.yaml # Configuration settings
└── test_*.py                  # Various test scripts
```

## Configuration

Edit `config/evaluation_config.yaml` to customize:

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

## Usage Example

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

## Development Status

### Implemented ✅
- Core evaluation framework with hierarchical structure
- Style guide page fetching and evaluation
- Basic test scripts with Gemma 3 integration
- Caching and performance optimization structure

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
python test.py

# Test the evaluation framework
python test_framework.py

# Test web scraping functionality
python test_scraping.py

# Test word substitution table usage
python test_word_table.py
```

## API Keys

The framework supports multiple LLM providers:

1. **Google AI Studio** (Recommended for testing - free tier available)
   - Get key from: https://aistudio.google.com/apikey
   - Models: Gemma 3 27B-IT

2. **OpenAI** (Optional - for senior/editor roles)
   - Models: GPT-4o, GPT-4o-mini

3. **Anthropic** (Optional)
   - Models: Claude 3 family

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
