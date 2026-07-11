import asyncio
import logging
from bot.database.db import database
from railway.client import RailwayClient
from bot.deployment.engine import deployment_engine
from bot.services.log_service import owner_log

logger = logging.getLogger(__name__)


class CleanupService:
    def __init__(self):
        self._task = None
        self._running = False

    async def start(self, interval: int = 1800):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop(interval))
        logger.info(f"CleanupService started (interval={interval}s)")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None

    async def _run_loop(self, interval: int):
        while self._running:
            try:
                await self._cleanup_all_tokens()
            except Exception as e:
                logger.error(f"Cleanup cycle error: {e}")
            await asyncio.sleep(interval)

    async def _check_token_health(self, token_doc: dict) -> bool:
        """Validate a token. If dead, disable it and migrate its deployments."""
        r_client = RailwayClient(token_doc["token"])
        try:
            info = await asyncio.wait_for(r_client.get_account_info(), timeout=15)
            if info.get("me", {}).get("id"):
                return True
            raise Exception("Invalid token response")
        except Exception:
            logger.warning(f"Token {token_doc['token'][:12]}... is DEAD, disabling and migrating")
            await database.disable_token(token_doc["token"])
            deps = await database.db.deployments.find({"railway_token": token_doc["token"]}).to_list(None)
            for dep in deps:
                try:
                    await deployment_engine.migrate_deployment(dep["deployment_id"])
                    await owner_log.send_log("token_restricted", {
                        "token": f"{token_doc['token'][:12]}...",
                        "deployment_id": dep["deployment_id"][:8],
                        "reason": "dead token - auto migrated",
                    })
                except Exception as e:
                    logger.error(f"Migration failed for {dep['deployment_id']}: {e}")
            return False
        finally:
            await r_client.close()

    async def _cleanup_all_tokens(self):
        tokens = await database.get_all_tokens()
        summary = {"scanned": 0, "deleted": 0, "errors": 0, "dead": 0, "tokens_checked": len(tokens)}
        for tdoc in tokens:
            if not tdoc.get("is_active"):
                continue
            if tdoc.get("is_restricted"):
                continue
            summary["scanned"] += 1

            # Step 1: Check token is alive
            alive = await self._check_token_health(tdoc)
            if not alive:
                summary["dead"] += 1
                continue

            # Step 2: Cleanup orphan projects
            r_client = RailwayClient(tdoc["token"])
            try:
                projects = await r_client.list_all_projects()
                for proj in projects:
                    pid = proj["id"]
                    services = await r_client.get_project_services_status(pid)
                    all_dead = True
                    for svc in services:
                        dep_edge = svc.get("deployments", {}).get("edges", [])
                        if not dep_edge:
                            continue
                        status = (dep_edge[0].get("node", {}).get("status") or "").upper()
                        if status in ("SUCCESS", "RUNNING", "BUILDING", "QUEUED", "DEPLOYING"):
                            all_dead = False
                            break
                    if all_dead and services:
                        db_dep = await database.db.deployments.find_one({"project_id": pid})
                        if not db_dep:
                            try:
                                await r_client.delete_project(pid)
                                summary["deleted"] += 1
                                await owner_log.send_log("orphan_cleanup", {
                                    "project": proj.get("name", pid),
                                    "project_id": pid,
                                    "token": f"{tdoc['token'][:12]}...",
                                })
                            except Exception as e:
                                summary["errors"] += 1
                                logger.error(f"Failed to delete orphan project {pid}: {e}")
            except Exception as e:
                summary["errors"] += 1
                logger.error(f"Cleanup error for token {tdoc['token'][:12]}: {e}")
            finally:
                await r_client.close()

        if summary["deleted"] > 0 or summary["errors"] > 0 or summary["dead"] > 0:
            await owner_log.send_log("token_cleanup_summary", {
                "tokens_checked": str(summary["tokens_checked"]),
                "scanned": str(summary["scanned"]),
                "dead_found": str(summary["dead"]),
                "orphan_deleted": str(summary["deleted"]),
                "errors": str(summary["errors"]),
            })


cleanup_service = CleanupService()
