import asyncio
import logging
from bot.database.db import database
from bot.deployment.engine import deployment_engine
from railway.token_manager import token_manager
from railway.client import RailwayClient

logger = logging.getLogger(__name__)


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

    async def _run_health_checker(self):
        while self._running:
            try:
                await self._check_deployments()
            except Exception as e:
                logger.error(f"Health check error: {e}")
            await asyncio.sleep(60)

    async def _run_token_rotator(self):
        while self._running:
            try:
                await self._rotate_tokens()
            except Exception as e:
                logger.error(f"Token rotation error: {e}")
            await asyncio.sleep(300)

    async def _check_deployments(self):
        all_deployments = await database.db.deployments.find({"status": {"$in": ["running", "deploying", "starting"]}}).to_list(None)
        for dep in all_deployments:
            try:
                token_doc = await database.get_railway_token(dep["railway_token"])
                if not token_doc or not token_doc.get("is_active"):
                    logger.warning(f"Token invalid for deployment {dep['deployment_id']}, migrating...")
                    await deployment_engine.migrate_deployment(dep["deployment_id"])
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

    async def _rotate_tokens(self):
        all_tokens = await database.get_all_tokens()
        for token_doc in all_tokens:
            if not token_doc.get("is_active"):
                continue
            client = RailwayClient(token_doc["token"])
            try:
                valid = await client.validate_token()
                if not valid:
                    logger.warning(f"Token {token_doc['token'][:8]}... invalid, disabling")
                    await database.disable_token(token_doc["token"])
                    continue
                info = await client.get_account_info()
                workspaces = info.get("me", {}).get("workspaces", [])
                credits = 0.0
                if workspaces:
                    customer = workspaces[0].get("customer", {})
                    credits = customer.get("remainingUsageCreditBalance")
                    if credits is None:
                        credit_bal = customer.get("creditBalance", -5.0)
                        credits = abs(credit_bal) if credit_bal is not None else 5.0
                else:
                    credits = 5.0
                
                if credits <= 0:
                    logger.warning(f"Token {token_doc['token'][:8]}... out of credits ({credits})")
                    await database.disable_token(token_doc["token"])
                    continue
                await database.db.railway_tokens.update_one(
                    {"token": token_doc["token"]},
                    {"$set": {"credits": credits}}
                )
            except Exception as e:
                logger.error(f"Token rotation check error: {e}")
            finally:
                await client.close()

        try:
            active_count = await database.count_active_tokens()
            if active_count < 2:
                from bot.services.log_service import owner_log
                await owner_log.send_log(
                    "token_warning",
                    **{
                        "error": "CRITICAL: Low active tokens!",
                        "reason": f"Only {active_count} active tokens remaining. Please add more Railway tokens immediately!"
                    }
                )
        except Exception as alert_err:
            logger.error(f"Failed to check token alert: {alert_err}")


deployment_worker = DeploymentWorker()
