import time
from dataclasses import dataclass
from urllib.parse import urljoin

import httpx

from app.encryption import decrypt_value
from app.config import SSL_VERIFY


@dataclass
class AdminAPISession:
    base_url: str
    username: str
    password: str
    cookie: str | None = None
    cookie_expiry: float = 0.0

    async def _login(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=15, verify=SSL_VERIFY) as client:
                resp = await client.post(
                    urljoin(self.base_url, "/login-submit"),
                    data={"username": self.username, "password": self.password},
                    follow_redirects=False,
                )
                if resp.status_code == 302:
                    for cookie_header in resp.headers.get_list("set-cookie"):
                        if cookie_header.startswith("oa_session="):
                            self.cookie = cookie_header.split(";")[0].split("=", 1)[1]
                            self.cookie_expiry = time.time() + (12 * 3600) - 600
                            return True
            return False
        except Exception:
            return False

    async def _ensure_session(self) -> bool:
        if self.cookie and time.time() < self.cookie_expiry:
            return True
        return await self._login()

    async def _request(self, method: str, path: str, json_data: dict | None = None, params: dict | None = None, timeout: int = 30) -> dict:
        ok = await self._ensure_session()
        if not ok:
            return {"error": "admin_api_login_failed", "detail": "Could not authenticate to server admin API"}

        headers = {}
        if self.cookie:
            headers["Cookie"] = f"oa_session={self.cookie}"

        try:
            async with httpx.AsyncClient(timeout=timeout, verify=SSL_VERIFY) as client:
                if method == "GET":
                    resp = await client.get(urljoin(self.base_url, path), headers=headers, params=params)
                elif method == "POST":
                    resp = await client.post(urljoin(self.base_url, path), headers=headers, json=json_data)

                if resp.status_code == 401:
                    self.cookie = None
                    ok = await self._login()
                    if not ok:
                        return {"error": "admin_api_login_failed"}
                    headers["Cookie"] = f"oa_session={self.cookie}"
                    if method == "GET":
                        resp = await client.get(urljoin(self.base_url, path), headers=headers, params=params)
                    else:
                        resp = await client.post(urljoin(self.base_url, path), headers=headers, json=json_data)

                if resp.status_code >= 400:
                    try:
                        return resp.json()
                    except Exception:
                        return {"error": f"http_{resp.status_code}", "detail": resp.text[:500]}
                return resp.json()
        except Exception as e:
            return {"error": "connection_failed", "detail": str(e)}

    async def get_instances(self) -> dict:
        return await self._request("GET", "/api/instances")

    async def get_health(self) -> dict:
        # The socket probe behind serving/wedged costs up to 5s per unresponsive
        # instance, so this one needs far more headroom than the default.
        return await self._request("GET", "/api/health", timeout=120)

    async def get_status(self) -> dict:
        return await self._request("GET", "/api/status")

    async def get_logs(self, instance: str) -> dict:
        return await self._request("GET", f"/api/logs/{instance}")

    async def get_broker_status(self, instance: str) -> dict:
        return await self._request("GET", f"/api/broker-status/{instance}")

    async def restart_instance(self, instance: str) -> dict:
        return await self._request("POST", "/api/restart-instance", json_data={"instance": instance})

    async def stop_instance(self, instance: str) -> dict:
        return await self._request("POST", "/api/stop-instance", json_data={"instance": instance})

    async def start_instance(self, instance: str) -> dict:
        return await self._request("POST", "/api/start-instance", json_data={"instance": instance})

    async def restart_all(self) -> dict:
        return await self._request("POST", "/api/restart-all")

    async def reboot_server(self) -> dict:
        return await self._request("POST", "/api/reboot-server")

    async def health_check(self, scope: str = "all", instance: str | None = None) -> dict:
        return await self._request("POST", "/api/health-check", json_data={"scope": scope, "instance": instance})

    async def update(self, scope: str = "all", instance: str | None = None) -> dict:
        return await self._request("POST", "/api/update", json_data={"scope": scope, "instance": instance})

    async def get_scripts_status(self) -> dict:
        return await self._request("GET", "/api/scripts-status")

    async def get_job_status(self, job_id: str) -> dict:
        return await self._request("GET", f"/api/jobs/{job_id}")

    async def health_liveness(self) -> dict:
        return await self._request("GET", "/health")
