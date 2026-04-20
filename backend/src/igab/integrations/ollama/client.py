import httpx


class OllamaClient:
    def __init__(self, host: str, model: str) -> None:
        self.host = host.rstrip("/")
        self.model = model

    async def generate(self, prompt: str, system: str | None = None) -> str:
        payload: dict = {"model": self.model, "prompt": prompt, "stream": False}
        if system:
            payload["system"] = system
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(f"{self.host}/api/generate", json=payload)
            resp.raise_for_status()
            return resp.json()["response"]

    async def health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self.host}/")
                return resp.status_code < 500
        except Exception:
            return False
