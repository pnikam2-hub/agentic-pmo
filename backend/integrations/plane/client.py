"""Plane client — throttled, paginated, read-only.

Plane enforces 60 requests/minute per API token, so every call is paced. The client never writes:
this module is the read half of the integration, and keeping it read-only is what makes it safe to
run against a live board while the write half is still being built.
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request


class PlaneError(RuntimeError):
    """Raised when Plane answers with a status the caller cannot handle."""


class PlaneClient:
    def __init__(self, base_url: str, workspace: str, api_key: str,
                 min_interval: float = 1.05, max_retries: int = 5, timeout: int = 30):
        if not base_url or not workspace or not api_key:
            raise PlaneError("base_url, workspace and api_key are all required")
        self.base_url = base_url.rstrip("/")
        self.workspace = workspace
        self.api_key = api_key
        self.min_interval = min_interval
        self.max_retries = max_retries
        self.timeout = timeout
        self.calls = 0
        self._last = 0.0

    # ── transport ────────────────────────────────────────────────────────────
    @property
    def api_root(self) -> str:
        return f"{self.base_url}/api/v1/workspaces/{self.workspace}"

    def _pace(self):
        gap = self.min_interval - (time.time() - self._last)
        if gap > 0:
            time.sleep(gap)

    def get(self, path: str, params: dict | None = None) -> dict:
        url = self.api_root + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        last_err = None
        for attempt in range(self.max_retries):
            self._pace()
            req = urllib.request.Request(
                url, method="GET",
                headers={"X-API-Key": self.api_key, "Accept": "application/json"},
            )
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    self._last = time.time()
                    self.calls += 1
                    raw = resp.read().decode() or "{}"
                    return json.loads(raw)
            except urllib.error.HTTPError as exc:
                self._last = time.time()
                body = exc.read().decode()[:300]
                if exc.code == 429:
                    retry_after = exc.headers.get("Retry-After")
                    wait = float(retry_after) if retry_after else 5.0 * (attempt + 1)
                    time.sleep(min(wait, 60))
                    last_err = f"429 throttled, retried {attempt + 1}x"
                    continue
                raise PlaneError(f"GET {path} -> {exc.code}: {body}") from exc
            except urllib.error.URLError as exc:
                self._last = time.time()
                last_err = str(exc.reason)
                time.sleep(2 * (attempt + 1))
                continue
        raise PlaneError(f"GET {path} failed after {self.max_retries} attempts: {last_err}")

    def paginate(self, path: str, params: dict | None = None, max_items: int = 5000):
        """Yield items across cursor pages. Plane caps per_page at 100."""
        params = dict(params or {})
        params.setdefault("per_page", 100)
        cursor = None
        seen = 0
        while True:
            page_params = dict(params)
            if cursor:
                page_params["cursor"] = cursor
            data = self.get(path, page_params)
            results = data.get("results", data if isinstance(data, list) else [])
            for item in results:
                yield item
                seen += 1
                if seen >= max_items:
                    return
            cursor = data.get("next_cursor")
            if not data.get("next_page_results") or not cursor:
                return

    # ── resources ────────────────────────────────────────────────────────────
    def projects(self):
        return list(self.paginate("/projects/"))

    def states(self, plane_project_id: str):
        return list(self.paginate(f"/projects/{plane_project_id}/states/"))

    def work_items(self, plane_project_id: str):
        return list(self.paginate(f"/projects/{plane_project_id}/work-items/"))

    def relations(self, plane_project_id: str, work_item_id: str) -> dict:
        return self.get(f"/projects/{plane_project_id}/work-items/{work_item_id}/relations/")

    def work_item(self, plane_project_id: str, work_item_id: str) -> dict:
        return self.get(f"/projects/{plane_project_id}/work-items/{work_item_id}/")
