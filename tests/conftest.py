"""Test settings shared by every test module."""
import os

# Tests never send traces to LangSmith, even if the developer's .env turns tracing
# on (load_dotenv does not override variables that are already set).
os.environ["LANGSMITH_TRACING"] = "false"
