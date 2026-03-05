"""
Infrastructure Monitor — Butler Agent Skill Module

Checks health of Docker containers, PostgreSQL, and API endpoint.
Returns a structured InfraStatus dict usable by alert logic.
"""

import asyncio
import shutil
import subprocess
import time
from dataclasses import dataclass, asdict
from typing import List, Optional
from datetime import datetime

import httpx

from src.utils.logger import setup_logger

logger = setup_logger(__name__)


@dataclass
class ServiceHealth:
    name:    str
    status:  str        # "ok" | "degraded" | "down"
    latency_ms: Optional[float] = None
    detail:  Optional[str] = None


@dataclass
class InfraStatus:
    timestamp: str
    overall:   str       # "ok" | "degraded" | "critical"
    services:  List[ServiceHealth]

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "overall":   self.overall,
            "services":  [asdict(s) for s in self.services],
        }

    @property
    def has_critical(self) -> bool:
        return any(s.status == "down" for s in self.services)

    @property
    def has_degraded(self) -> bool:
        return any(s.status == "degraded" for s in self.services)


async def _check_api_health(base_url: str = "http://localhost:8000") -> ServiceHealth:
    """Probe the FastAPI /health endpoint."""
    try:
        t0 = time.monotonic()
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{base_url}/health")
        latency = round((time.monotonic() - t0) * 1000, 1)
        if r.status_code == 200:
            return ServiceHealth("api", "ok", latency)
        return ServiceHealth("api", "degraded", latency, f"HTTP {r.status_code}")
    except Exception as e:
        return ServiceHealth("api", "down", detail=str(e)[:120])


async def _check_database(database_url: str) -> ServiceHealth:
    """Run a trivial async query to verify DB connectivity."""
    try:
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy import text
        t0 = time.monotonic()
        engine = create_async_engine(database_url, pool_pre_ping=True)
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        await engine.dispose()
        latency = round((time.monotonic() - t0) * 1000, 1)
        return ServiceHealth("postgresql", "ok", latency)
    except Exception as e:
        return ServiceHealth("postgresql", "down", detail=str(e)[:120])


def _check_docker_containers() -> List[ServiceHealth]:
    """
    Run `docker ps --format '{{.Names}}\t{{.Status}}'` synchronously in a thread.
    Returns a health entry per container.
    """
    results: List[ServiceHealth] = []
    if not shutil.which("docker"):
        # For environments explicitly lacking the docker binary (e.g. some PaaS),
        # return an OK status with a note instead of degrading the whole system.
        results.append(ServiceHealth("docker", "ok", detail="Docker not installed/required in this environment"))
        return results

    try:
        proc = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}\t{{.Status}}"],
            capture_output=True, text=True, timeout=10
        )
        if proc.returncode != 0:
            results.append(ServiceHealth("docker", "down", detail=proc.stderr[:120]))
            return results

        for line in proc.stdout.strip().splitlines():
            parts = line.split("\t", 1)
            if len(parts) == 2:
                name, status = parts
                ok = "Up" in status
                results.append(ServiceHealth(
                    name=f"docker:{name}",
                    status="ok" if ok else "degraded",
                    detail=status[:60],
                ))
        if not results:
            results.append(ServiceHealth("docker", "ok", detail="No containers running"))
    except FileNotFoundError:
        results.append(ServiceHealth("docker", "degraded", detail="docker binary not found"))
    except Exception as e:
        results.append(ServiceHealth("docker", "down", detail=str(e)[:120]))
    return results


async def run_infra_check(database_url: str, api_base: str = "http://localhost:8000") -> InfraStatus:
    """Full infrastructure health check. Safe to call from async context."""
    api_health, db_health = await asyncio.gather(
        _check_api_health(api_base),
        _check_database(database_url),
    )
    docker_services = await asyncio.to_thread(_check_docker_containers)

    all_services = [api_health, db_health] + docker_services

    if any(s.status == "down" for s in all_services):
        overall = "critical"
    elif any(s.status == "degraded" for s in all_services):
        overall = "degraded"
    else:
        overall = "ok"

    return InfraStatus(
        timestamp=datetime.utcnow().isoformat(),
        overall=overall,
        services=all_services,
    )
