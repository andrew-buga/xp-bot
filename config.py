import os


def _load_local_dotenv(path: str = ".env") -> None:
    if not os.path.exists(path):
        return

    with open(path, "r", encoding="utf-8") as dotenv_file:
        for line in dotenv_file:
            raw = line.strip()
            if not raw or raw.startswith("#") or "=" not in raw:
                continue
            key, value = raw.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _parse_admin_ids(value: str) -> list[int]:
    items = [item.strip() for item in value.split(",")]
    ids: list[int] = []
    for item in items:
        if not item:
            continue
        try:
            ids.append(int(item))
        except ValueError as exc:
            raise RuntimeError(
                "ADMIN_IDS must be a comma-separated list of integers"
            ) from exc
    if not ids:
        raise RuntimeError("ADMIN_IDS must contain at least one Telegram user ID")
    return ids


_load_local_dotenv()

BOT_TOKEN = _require_env("BOT_TOKEN")
ADMIN_IDS = _parse_admin_ids(_require_env("ADMIN_IDS"))
CHANNEL_ID = _require_env("CHANNEL_ID")
