import asyncio
import logging
from bot.database.db import database
from bot.deployment.engine import deployment_engine
from railway.token_manager import token_manager
from railway.client import RailwayClient
from bot.utils.security import is_permanent_token_error

logger = logging.getLogger(__name__)

# Railway statuses that mean "not running"
DEAD_STATUSES = {"CRASHED", "FAILED", "REMOVED", "SLEEPING", "SKIPPED", "WAITING"}
RUNNING_STATUSES = {"SUCCESS", "RUNNING", "BUILDING", "INITIALIZING", "QUEUED", "DEPLOYING"}


class DeploymentWorker:
    def __init__(self):
        self._running = False

    async def start(self):
        self._running = True
        asyncio.create_task(self._run_health_checker())
        asyncio.create_task(self._run_token_rotator())
        logger.info("Deployment worker started")

    async def stop(self):
        self._running = False

    # ─────────────────────────────────────────────
    # Health Checker — every 60s
    # ─────────────────────────────────────────────
    async def _run_health_checker(self):
        while self._running:
            try:
                await self._check_deployments()
            except Exception as e:
                logger.error(f"Health check error: {e}")
            await asyncio.sleep(60)

    async def _check_deployments(self):
        all_deployments = await database.db.deployments.find(
            {"status": {"$in": ["running", "deploying", "starting"]}}
        ).to_list(None)

        for dep in all_deployments:
            try:
                token_doc = await database.get_railway_token(dep["railway_token"])
                if not token_doc or not token_doc.get("is_active") or token_doc.get("credits", 5.0) <= 0:
                    logger.warning(f"Token invalid or exhausted for deployment {dep['deployment_id']}, migrating...")
                    success = await deployment_engine.migrate_deployment(dep["deployment_id"])
                    if not success:
                        await database.update_deployment(dep["deployment_id"], {"status": "suspended"})
                        logger.error(f"Migration failed for deployment {dep['deployment_id']}, marked as suspended")
                    continue
                client = RailwayClient(dep["railway_token"])
                try:
                    result = await client.get_deployment(dep["railway_deployment_id"])
                    if result and result.get("deployment"):
                        status = result["deployment"].get("status", "unknown")
                        if status in ("crashed", "failed", "sleeping"):
                            await deployment_engine.restart_deployment(dep["deployment_id"])
                            logger.info(f"Restarted deployment {dep['deployment_id']} due to status: {status}")
                except Exception as e:
                    logger.error(f"Health check failed for {dep['deployment_id']}: {e}")
                finally:
                    await client.close()
            except Exception as e:
                logger.error(f"Deployment check error: {e}")

    # ─────────────────────────────────────────────
    # Token Rotator — every 5 minutes
    # ─────────────────────────────────────────────
    async def _run_token_rotator(self):
        while self._running:
            try:
                await self._rotate_tokens()
            except Exception as e:
                logger.error(f"Token rotation error: {e}")
            await asyncio.sleep(300)

    async def _rotate_tokens(self):
        from bot.services.log_service import owner_log

        all_tokens = await database.get_all_tokens()

        for token_doc in all_tokens:
            token = token_doc["token"]
            token_short = token[:8] + "..."
            client = RailwayClient(token)

            try:
                # ── Step 1: Validate token ──────────────────────────────
                try:
                    valid = await asyncio.wait_for(client.validate_token(), timeout=20)
                    if not valid:
                        if token_doc.get("is_active"):
                            logger.warning(f"Token {token_short} is invalid/restricted — disabling")
                            await database.disable_token(token)
                            await owner_log.send_log(
                                "token_restricted",
                                token=token_short,
                                reason="Token validation failed (invalid, expired, or restricted by Railway)",
                                status="DISABLED",
                            )
                        continue
                except asyncio.TimeoutError:
                    logger.warning(f"Timeout validating token {token_short} — skipping rotation check for now")
                    continue

                # ── Step 2: Check credits ───────────────────────────────
                try:
                    info = await asyncio.wait_for(client.get_account_info(), timeout=20)
                except asyncio.TimeoutError:
                    info = {}

                workspaces = info.get("me", {}).get("workspaces", [])
                credits = 5.0
                if workspaces:
                    customer = workspaces[0].get("customer", {})
                    credits = customer.get("remainingUsageCreditBalance")
                    if credits is None:
                        credit_bal = customer.get("creditBalance", -5.0)
                        credits = abs(credit_bal) if credit_bal is not None else 5.0

                if credits <= 0 and token_doc.get("is_active"):
                    logger.warning(f"Token {token_short} exhausted credits ({credits}) — disabling")
                    await database.disable_token(token)
                    await owner_log.send_log(
                        "token_exhausted",
                        token=token_short,
                        credits=str(credits),
                        reason="Token has 0 or negative credit balance",
                        status="DISABLED",
                    )
                    continue

                # Update credits in DB
                await database.db.railway_tokens.update_one(
                    {"token": token},
                    {"$set": {"credits": credits}}
                )

                # ── Step 3: Orphan project cleanup ──────────────────────
                if token_doc.get("is_active"):
                    await self._cleanup_orphan_projects(client, token, token_short, owner_log)

            except Exception as e:
                logger.error(f"Token rotation check error for {token_short}: {e}")
            finally:
                await client.close()

        # ── Step 4: Alert if low active tokens ──────────────────────────
        try:
            from bot.services.log_service import owner_log
            active_count = await database.count_active_tokens()
            if active_count < 2:
                await owner_log.send_log(
                    "token_warning",
                    error="CRITICAL: Low active tokens!",
                    reason=f"Only {active_count} active token(s) remaining. Add more Railway tokens immediately!",
                )
        except Exception as alert_err:
            logger.error(f"Failed to check token alert: {alert_err}")

    # ─────────────────────────────────────────────
    # Orphan Project Cleanup
    # ─────────────────────────────────────────────
    async def _cleanup_orphan_projects(self, client: RailwayClient, token: str, token_short: str, owner_log):
        """
        Fetch all projects on Railway for this token.
        Delete any pbc-prefixed project that:
          a) Is not tracked in our DB, OR
          b) Is tracked in DB but has status stopped/failed/crashed AND
             all Railway services are DEAD (not running).
        """
        try:
            all_railway_projects = await asyncio.wait_for(
                client.list_all_projects(), timeout=30
            )
        except asyncio.TimeoutError:
            logger.warning(f"Timeout listing projects for token {token_short}")
            return
        except Exception as e:
            logger.error(f"Failed to list projects for {token_short}: {e}")
            return

        if not all_railway_projects:
            return

        # Collect all project_ids tracked in our DB for this token
        try:
            db_deployments = await database.db.deployments.find(
                {"railway_token": token}
            ).to_list(None)
        except Exception:
            db_deployments = []

        db_project_ids = {dep["project_id"] for dep in db_deployments if dep.get("project_id")}
        db_active_project_ids = {
            dep["project_id"]
            for dep in db_deployments
            if dep.get("project_id") and dep.get("status") in ("running", "deploying", "starting")
        }

        deleted_count = 0
        skipped_count = 0

        for project in all_railway_projects:
            project_id = project.get("id")
            project_name = project.get("name", "")

            # Only touch our own projects (pbc- prefix)
            if not project_name.startswith("pbc-"):
                skipped_count += 1
                continue

            # If project is actively running in our DB — skip it
            if project_id in db_active_project_ids:
                skipped_count += 1
                continue

            # If project is not in DB at all → orphan, delete
            if project_id not in db_project_ids:
                await self._delete_orphan_project(
                    client, project_id, project_name, token_short,
                    reason="Not tracked in DB (orphan)", owner_log=owner_log
                )
                deleted_count += 1
                await asyncio.sleep(0.5)  # Rate limit
                continue

            # Project is in DB but status is stopped/failed → check Railway services
            try:
                services = await asyncio.wait_for(
                    client.get_project_services_status(project_id), timeout=15
                )
            except Exception:
                continue

            # If ALL services are dead → delete
            if services and all(
                (svc.get("latest_status") or "").upper() in DEAD_STATUSES or svc.get("latest_status") is None
                for svc in services
            ):
                await self._delete_orphan_project(
                    client, project_id, project_name, token_short,
                    reason=f"All services dead ({[s.get('latest_status') for s in services]})",
                    owner_log=owner_log
                )
                # Also mark DB deployment as deleted
                for dep in db_deployments:
                    if dep.get("project_id") == project_id:
                        await database.update_deployment(dep["deployment_id"], {"status": "deleted_cleanup"})
                deleted_count += 1
                await asyncio.sleep(0.5)

        if deleted_count > 0:
            logger.info(f"Token {token_short}: Deleted {deleted_count} dead/orphan projects, skipped {skipped_count}")
            try:
                await owner_log.send_log(
                    "token_cleanup_summary",
                    token=token_short,
                    deleted=str(deleted_count),
                    skipped=str(skipped_count),
                    total_on_railway=str(len(all_railway_projects)),
                )
            except Exception as log_err:
                logger.error(f"Failed to send cleanup summary log: {log_err}")

    async def _delete_orphan_project(
        self, client: RailwayClient, project_id: str, project_name: str,
        token_short: str, reason: str, owner_log
    ):
        try:
            success = await asyncio.wait_for(
                client.delete_project(project_id), timeout=15
            )
            if success:
                logger.info(f"Deleted orphan project '{project_name}' ({project_id[:8]}) from token {token_short}")
                await owner_log.send_log(
                    "orphan_cleanup",
                    token=token_short,
                    project=project_name,
                    project_id=project_id[:12],
                    reason=reason,
                    result="✅ DELETED",
                )
            else:
                logger.warning(f"Failed to delete orphan project {project_name} ({project_id[:8]})")
        except asyncio.TimeoutError:
            logger.warning(f"Timeout deleting project {project_name}")
        except Exception as e:
            logger.error(f"Error deleting orphan project {project_name}: {e}")


deployment_worker = DeploymentWorker()
