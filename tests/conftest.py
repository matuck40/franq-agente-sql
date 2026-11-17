"""Test settings shared by every test module."""
import os

# Tests never send traces to LangSmith, even if the developer's .env turns tracing
# on (load_dotenv does not override variables that are already set).
# The *_TRACING_V2 names are checked first by langsmith, so turn them off too.
for nome in ("LANGSMITH_TRACING", "LANGSMITH_TRACING_V2", "LANGCHAIN_TRACING_V2"):
    os.environ[nome] = "false"
