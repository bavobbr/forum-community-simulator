import os

# Set up environment variables before any imports of modules that depend on them
os.environ.setdefault("GOOGLE_API_KEY", "test-api-key-for-unit-tests")
