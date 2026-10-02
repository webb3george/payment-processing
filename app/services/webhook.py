from typing import Any

import httpx


class WebhookDeliveryError(Exception):
    """Webhook не доставлен: сетевая ошибка, таймаут или не-2xx ответ."""


class WebhookSender:
    def __init__(self, *, timeout: float) -> None:
        self._client = httpx.AsyncClient(timeout=timeout)

    async def send(self, url: str, payload: dict[str, Any]) -> None:
        try:
            response = await self._client.post(url, json=payload)
        except (httpx.HTTPError, httpx.InvalidURL) as exc:
            raise WebhookDeliveryError(f"request to {url} failed: {exc!r}") from exc
        if not response.is_success:
            raise WebhookDeliveryError(f"{url} responded with {response.status_code}")

    async def aclose(self) -> None:
        await self._client.aclose()