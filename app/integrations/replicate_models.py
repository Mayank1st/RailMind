"""
Replicate model registry — the only file to touch when adding a model.

Add one line per model and you're done; REPLICATE_MODELS picks it up
automatically. Anywhere in the app (or from an FE payload) pass the key
("MODEL1") to replicate_client()/run_replicate_model() and the matching
Replicate model is called.

    MODEL2 = "google/gemini-2.5-flash"
    MODEL3 = "anthropic/claude-4.5-haiku"
"""

MODEL1 = "openai/gpt-5-nano"
MODEL2 = "google/nano-banana-2"  # image generation (weekly city carousel)
MODEL3 = "openai/gpt-5-mini"

REPLICATE_MODELS: dict[str, str] = {
    name: value
    for name, value in dict(globals()).items()
    if name.startswith("MODEL") and isinstance(value, str)
}
