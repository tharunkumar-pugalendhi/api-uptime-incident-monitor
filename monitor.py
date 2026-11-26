
import logging
import time

import httpx

from database import get_conn, now_utc


logger = logging.getLogger(__name__)


async def check_single_endpoint(endpoint_id: int):
    conn = get_conn()

    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM endpoints WHERE id = ?",
            (endpoint_id,)
        )
        ep = cur.fetchone()

        if not ep:
            logger.warning("Endpoint %s was not found", endpoint_id)
            return None

        url = ep["url"]
        sla_ms = ep["sla_ms"]
        checked_at = now_utc()

        status_code = None
        latency_ms = 0.0
        reason = ""

        start = time.perf_counter()

        try:
            async with httpx.AsyncClient(
                timeout=8.0,
                follow_redirects=False
            ) as client:
                response = await client.get(
                    url,
                    headers={"User-Agent": "APIPulseMonitor/1.0"}
                )

            latency_ms = round(
                (time.perf_counter() - start) * 1000, 1
            )
            status_code = response.status_code

            if 200 <= status_code < 300:
                if latency_ms <= sla_ms:
                    health_status = "HEALTHY"
                else:
                    health_status = "DEGRADED"
                    reason = (
                        f"SLA breach: {latency_ms}ms > {sla_ms}ms"
                    )
            else:
                health_status = "DOWN"
                reason = f"Unexpected HTTP {status_code}"

        except httpx.TimeoutException:
            latency_ms = round(
                (time.perf_counter() - start) * 1000, 1
            )
            health_status = "DOWN"
            reason = "Request timed out (>8000ms)"
            logger.warning(
                "Health check timed out for endpoint %s",
                endpoint_id
            )

        except httpx.RequestError as exc:
            latency_ms = round(
                (time.perf_counter() - start) * 1000, 1
            )
            health_status = "DOWN"
            reason = f"Connection error: {type(exc).__name__}"
            logger.warning(
                "HTTP request failed for endpoint %s: %s",
                endpoint_id,
                type(exc).__name__
            )

        except Exception as exc:
            latency_ms = round(
                (time.perf_counter() - start) * 1000, 1
            )
            health_status = "DOWN"
            reason = f"Unexpected error: {type(exc).__name__}"
            logger.exception(
                "Unexpected error while checking endpoint %s",
                endpoint_id
            )

        # Persist the check and incident changes as one transaction.
        try:
            cur.execute(
                """
                INSERT INTO check_logs
                (endpoint_id, status, status_code, latency_ms, checked_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    endpoint_id,
                    health_status,
                    status_code,
                    latency_ms,
                    checked_at
                )
            )

            cur.execute(
                """
                UPDATE endpoints
                SET current_status = ?,
                    last_status_code = ?,
                    last_latency_ms = ?,
                    last_checked_at = ?
                WHERE id = ?
                """,
                (
                    health_status,
                    status_code,
                    latency_ms,
                    checked_at,
                    endpoint_id
                )
            )

            cur.execute(
                """
                SELECT id FROM incidents
                WHERE endpoint_id = ? AND status = 'OPEN'
                LIMIT 1
                """,
                (endpoint_id,)
            )
            open_incident = cur.fetchone()

            if health_status == "DOWN" and not open_incident:
                cur.execute(
                    """
                    INSERT INTO incidents
                    (endpoint_id, endpoint_name, reason, status, opened_at)
                    VALUES (?, ?, ?, 'OPEN', ?)
                    """,
                    (
                        endpoint_id,
                        ep["name"],
                        reason,
                        checked_at
                    )
                )

            elif (
                health_status in ("HEALTHY", "DEGRADED")
                and open_incident
            ):
                cur.execute(
                    """
                    UPDATE incidents
                    SET status = 'RESOLVED', resolved_at = ?
                    WHERE id = ?
                    """,
                    (checked_at, open_incident["id"])
                )

            conn.commit()

        except Exception:
            conn.rollback()
            logger.exception(
                "Failed to save health-check results for endpoint %s",
                endpoint_id
            )
            raise

        return {
            "id": endpoint_id,
            "status": health_status,
            "latency_ms": latency_ms,
            "status_code": status_code
        }

    finally:
        conn.close()


async def check_all_endpoints():
    conn = get_conn()

    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM endpoints")
        ids = [row["id"] for row in cur.fetchall()]
    finally:
        conn.close()

    results = []

    for endpoint_id in ids:
        try:
            result = await check_single_endpoint(endpoint_id)
            results.append(result)

        except Exception as exc:
            logger.exception(
                "Health check failed unexpectedly for endpoint %s",
                endpoint_id
            )
            results.append({
                "id": endpoint_id,
                "status": "ERROR",
                "error": type(exc).__name__
            })

    return results
