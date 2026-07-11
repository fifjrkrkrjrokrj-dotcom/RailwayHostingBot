import asyncio
import io
import json
import logging
import os
import shutil
import time
import uuid
import zipfile
from typing import Optional

from bot.config.settings import settings
from bot.database.db import database
from bot.utils.formatters import detect_framework, detect_startup_file, is_python_project, parse_env_content, format_timestamp
from bot.utils.security import scan_zip_for_threats, validate_railway_token
from github.client import github_client
from railway.client import RailwayClient
from railway.token_manager import token_manager
from bot.services.log_service import owner_log

logger = logging.getLogger(__name__)

DEPLOY_CACHE = {}


class TerminalBuffer:
    def __init__(self, deployment_id: str):
        self.deployment_id = deployment_id
        self.lines = []
        self._subscribers = set()

    def add_line(self, line: str):
        timestamp = format_timestamp()
        formatted = f"[{timestamp}] {line}"
        self.lines.append(formatted)
        for ws in self._subscribers:
            try:
                ws.put_nowait(formatted)
            except Exception:
                pass

    def add_error(self, line: str):
        timestamp = format_timestamp()
        formatted = f"[{timestamp}] ❌ {line}"
        self.lines.append(formatted)
        for ws in self._subscribers:
            try:
                ws.put_nowait(formatted)
            except Exception:
                pass

    def subscribe(self, ws):
        self._subscribers.add(ws)
        for line in self.lines[-50:]:
            try:
                ws.put_nowait(line)
            except Exception:
                pass

    def unsubscribe(self, ws):
        self._subscribers.discard(ws)

    def get_recent(self, limit: int = 100) -> str:
        return "\n".join(self.lines[-limit:])

    def clear(self):
        self.lines.clear()


class DeploymentEngine:
    _terminals = {}

    def get_terminal(self, deployment_id: str) -> TerminalBuffer:
        if deployment_id not in self._terminals:
            self._terminals[deployment_id] = TerminalBuffer(deployment_id)
        return self._terminals[deployment_id]

    async def deploy_from_github(self, user_id: int, repo_url: str, variables: dict = None, scan_result: dict = None) -> dict:
        deployment_id = str(uuid.uuid4())
        extract_path = None
        terminal = self.get_terminal(deployment_id)
        terminal.add_line("starting deployment process...")

        parsed = github_client.parse_github_url(repo_url)
        if not parsed:
            terminal.add_error("invalid github url")
            return {"success": False, "error": "Invalid GitHub URL", "deployment_id": deployment_id}

        branch_display = parsed['branch'] or "default"
        terminal.add_line(f"repository: {parsed['owner']}/{parsed['repo']}")
        terminal.add_line(f"branch: {branch_display}")

        if scan_result is None:
            terminal.add_line("cloning repository...")
            try:
                scan_result = await asyncio.wait_for(
                    github_client.scan_repository(parsed["owner"], parsed["repo"], parsed["branch"]),
                    timeout=90,
                )
            except asyncio.TimeoutError:
                terminal.add_error("scan timed out — repository may be too large or GitHub is slow")
                return {"success": False, "error": "Repository scan timed out. Please try again.", "deployment_id": deployment_id}
        else:
            terminal.add_line("using pre-scanned repository data...")

        if not scan_result.get("success"):
            terminal.add_error(scan_result.get("error", "scan failed"))
            return {"success": False, "error": scan_result.get("error"), "deployment_id": deployment_id}

        terminal.add_line("repository scanned successfully")
        terminal.add_line(f"framework detected: {scan_result['framework']}")
        terminal.add_line(f"startup file: {scan_result['startup_file']}")

        if scan_result.get("has_requirements"):
            terminal.add_line("requirements.txt detected")
        if scan_result.get("has_runtime"):
            terminal.add_line("runtime.txt detected")
        if scan_result.get("has_dockerfile"):
            terminal.add_line("dockerfile detected")

        terminal.add_line("finding available railway token...")
        project = None
        token_doc = None
        client = None

        all_tokens = await database.get_all_tokens()
        max_retries = max(len(all_tokens) * 2, 10)
        retries = 0
        last_error = "Unknown error"
        while retries < max_retries:
            retries += 1
            token_doc = await token_manager.get_available_token()
            if not token_doc:
                terminal.add_error("no railway tokens available")
                return {"success": False, "error": "No Railway tokens available", "deployment_id": deployment_id}

            client = RailwayClient(token_doc["token"])
            project_id = None
            try:
                project_name = f"pbc-{user_id}-{int(time.time())}"
                project = await client.create_project(project_name)
                if not project:
                    raise Exception("API returned None")

                project_id = project.get("projectCreate", {}).get("id") or str(uuid.uuid4())
                terminal.add_line(f"project created: {project_id[:8]}...")

                env = await client.create_environment(project_id)
                env_id = env.get("environmentCreate", {}).get("id") or str(uuid.uuid4())

                repo_slug = f"{parsed['owner']}/{parsed['repo']}"
                service = await client.create_service(project_id, "bot-service", source_repo=repo_slug)
                service_id = service.get("serviceCreate", {}).get("id") or str(uuid.uuid4())
                terminal.add_line("service created and linked to github repository")

                from bot.deployment.engine import DEPLOY_CACHE
                region_code = None
                for d_id, d_data in DEPLOY_CACHE.items():
                    if d_data.get("user_id") == user_id:
                        region_code = d_data.get("region")
                        break

                if region_code:
                    terminal.add_line(f"configuring server region to {region_code}...")
                    await client.update_service_instance_region(service_id, env_id, region_code)

                if variables:
                    terminal.add_line("setting environment variables...")
                    for key, value in variables.items():
                        await client.set_environment_variable(project_id, env_id, key, value, service_id=service_id)

                terminal.add_line("generating railway public domain...")
                domain_doc = await client.create_service_domain(service_id, env_id)
                if domain_doc and domain_doc.get("domain"):
                    dep_url = f"https://{domain_doc['domain']}"
                    terminal.add_line(f"public domain created: {dep_url}")
                else:
                    dep_url = f"https://{project_id}.up.railway.app"

                dep_id = await client.create_deployment(service_id, env_id)
                if not dep_id:
                    raise Exception("Deployment creation failed on Railway API")

                terminal.add_line(f"deployment created: {dep_id[:8]}...")
                terminal.add_line("build started...")

                dep_record = {
                    "deployment_id": deployment_id,
                    "user_id": user_id,
                    "project_id": project_id,
                    "environment_id": env_id,
                    "service_id": service_id,
                    "railway_deployment_id": dep_id,
                    "railway_token": token_doc["token"],
                    "repo_url": repo_url,
                    "framework": scan_result["framework"],
                    "startup_file": scan_result["startup_file"],
                    "status": "deploying",
                    "url": dep_url,
                    "variables": variables or {},
                    "created_at": time.time(),
                    "last_active": time.time(),
                    "restart_count": 0,
                    "total_runtime": 0,
                }
                await database.create_deployment(dep_record)

                await self._send_log(
                    "new_deployment",
                    {
                        "user_id": user_id,
                        "deployment_id": deployment_id,
                        "repo": f"{parsed['owner']}/{parsed['repo']}",
                        "framework": scan_result["framework"],
                        "url": dep_url,
                        "token": f"TOKEN #{token_doc.get('priority', 0)}",
                        "variables": str(variables or {}),
                    },
                )

                await client.close()
                return {"success": True, "deployment_id": deployment_id, "url": dep_url, "framework": scan_result["framework"]}
            except Exception as e:
                last_error = str(e)
                terminal.add_error(f"token {token_doc['token'][:5]}... failed ({str(e)[:80]}). switching...")
                try:
                    await client.delete_project(project_id)
                except Exception:
                    pass
                await database.disable_token(token_doc["token"])
                await token_manager.release_token(token_doc["token"])
                await client.close()
                continue

        terminal.add_error(f"all tokens exhausted. last error: {last_error}")
        return {"success": False, "error": f"All Railway tokens exhausted. Last error: {last_error}", "deployment_id": deployment_id}

    async def deploy_from_zip(self, user_id: int, zip_data: bytes, variables: dict = None) -> dict:
        deployment_id = str(uuid.uuid4())
        extract_path = None
        terminal = self.get_terminal(deployment_id)
        terminal.add_line("starting zip deployment process...")

        terminal.add_line("scanning zip file...")
        zip_path = os.path.join(settings.TEMP_DIR, f"{uuid.uuid4()}.zip")
        with open(zip_path, "wb") as f:
            f.write(zip_data)
        threats = scan_zip_for_threats(zip_path)
        os.remove(zip_path)
        if threats:
            terminal.add_error(f"threats detected: {', '.join(threats[:3])}")
            return {"success": False, "error": "Security scan failed", "details": threats, "deployment_id": deployment_id}

        terminal.add_line("extracting zip...")
        try:
            files = []
            contents = {}
            with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    files.append(info.filename)
                    try:
                        contents[info.filename] = zf.read(info).decode("utf-8", errors="ignore")
                    except Exception:
                        contents[info.filename] = ""
        except Exception as e:
            terminal.add_error(f"extraction failed: {str(e)}")
            return {"success": False, "error": "ZIP extraction failed", "deployment_id": deployment_id}

        if not is_python_project(files):
            terminal.add_error("not a python project")
            return {"success": False, "error": "Only Python Telegram bots supported", "deployment_id": deployment_id}

        startup_file = detect_startup_file(files)
        framework = detect_framework(list(contents.values()))
        has_requirements = "requirements.txt" in files

        terminal.add_line(f"framework detected: {framework}")
        terminal.add_line(f"startup file: {startup_file}")
        if has_requirements:
            terminal.add_line("requirements.txt detected")

        terminal.add_line("finding available railway token...")
        last_error = "Unknown error"

        all_tokens = await database.get_all_tokens()
        max_retries = max(len(all_tokens) * 2, 10)
        retries = 0
        while retries < max_retries:
            retries += 1
            token_doc = await token_manager.get_available_token()
            if not token_doc:
                terminal.add_error("no railway tokens available")
                return {"success": False, "error": "No Railway tokens available", "deployment_id": deployment_id}

            client = RailwayClient(token_doc["token"])
            project_id = None
            extract_path = None
            try:
                project_name = f"pbc-{user_id}-{int(time.time())}"
                project = await client.create_project(project_name)
                if not project:
                    raise Exception("API returned None")

                project_id = project.get("projectCreate", {}).get("id") or str(uuid.uuid4())
                env = await client.create_environment(project_id)
                env_id = env.get("environmentCreate", {}).get("id") or str(uuid.uuid4())
                service = await client.create_service(project_id, "bot-service")
                service_id = service.get("serviceCreate", {}).get("id") or str(uuid.uuid4())

                from bot.deployment.engine import DEPLOY_CACHE
                region_code = None
                for d_id, d_data in DEPLOY_CACHE.items():
                    if d_data.get("user_id") == user_id:
                        region_code = d_data.get("region")
                        break

                if region_code:
                    terminal.add_line(f"configuring server region to {region_code}...")
                    await client.update_service_instance_region(service_id, env_id, region_code)

                if variables:
                    terminal.add_line("setting environment variables...")
                    for key, value in variables.items():
                        await client.set_environment_variable(project_id, env_id, key, value, service_id=service_id)

                extract_path = os.path.join(settings.TEMP_DIR, deployment_id)
                os.makedirs(extract_path, exist_ok=True)
                await github_client.extract_zip_to_path(zip_data, extract_path)
                terminal.add_line("source code extracted")

                terminal.add_line("uploading source code to railway via cli...")
                cmd = f'railway up --detach --json --project "{project_id}" --service "{service_id}" --environment "{env_id}"'
                env_vars = os.environ.copy()
                env_vars["RAILWAY_TOKEN"] = token_doc["token"]

                proc = await asyncio.create_subprocess_shell(
                    cmd,
                    cwd=extract_path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env_vars
                )
                stdout_bytes, stderr_bytes = await proc.communicate()

                if proc.returncode != 0:
                    err_msg = stderr_bytes.decode("utf-8", errors="ignore")
                    raise Exception(f"Railway CLI upload failed: {err_msg}")

                import re
                dep_id = None
                try:
                    stdout_str = stdout_bytes.decode("utf-8", errors="ignore")
                    import json
                    try:
                        data = json.loads(stdout_str)
                        dep_id = data.get("deploymentId") or data.get("id")
                    except Exception:
                        match = re.search(r'"(?:deployment)?Id"\s*:\s*"([^"]+)"', stdout_str)
                        if match:
                            dep_id = match.group(1)
                except Exception:
                    pass

                if not dep_id:
                    dep_id = str(uuid.uuid4())[:12]

                terminal.add_line("generating railway public domain...")
                domain_doc = await client.create_service_domain(service_id, env_id)
                if domain_doc and domain_doc.get("domain"):
                    dep_url = f"https://{domain_doc['domain']}"
                    terminal.add_line(f"public domain created: {dep_url}")
                else:
                    dep_url = f"https://{project_id}.up.railway.app"

                terminal.add_line(f"deployment created: {dep_id[:8]}...")
                terminal.add_line("build started...")

                dep_record = {
                    "deployment_id": deployment_id,
                    "user_id": user_id,
                    "project_id": project_id,
                    "environment_id": env_id,
                    "service_id": service_id,
                    "railway_deployment_id": dep_id,
                    "railway_token": token_doc["token"],
                    "repo_url": "ZIP Upload",
                    "framework": framework,
                    "startup_file": startup_file,
                    "status": "deploying",
                    "url": dep_url,
                    "variables": variables or {},
                    "created_at": time.time(),
                    "last_active": time.time(),
                    "restart_count": 0,
                    "total_runtime": 0,
                }
                await database.create_deployment(dep_record)

                try:
                    zips_dir = os.path.join("data", "zips")
                    os.makedirs(zips_dir, exist_ok=True)
                    zip_save_path = os.path.join(zips_dir, f"{deployment_id}.zip")
                    with open(zip_save_path, "wb") as f:
                        f.write(zip_data)
                except Exception as zip_err:
                    logger.error(f"Failed to save zip backup: {zip_err}")

                await self._send_log(
                    "new_deployment",
                    {
                        "user_id": user_id,
                        "deployment_id": deployment_id,
                        "repo": "ZIP Upload",
                        "framework": framework,
                        "url": dep_url,
                        "token": f"TOKEN #{token_doc.get('priority', 0)}",
                        "variables": str(variables or {}),
                    },
                )

                if extract_path:
                    shutil.rmtree(extract_path, ignore_errors=True)
                await client.close()
                return {"success": True, "deployment_id": deployment_id, "url": dep_url, "framework": framework}
            except Exception as e:
                last_error = str(e)
                terminal.add_error(f"token {token_doc['token'][:5]}... failed ({str(e)[:80]}). switching...")
                try:
                    await client.delete_project(project_id)
                except Exception:
                    pass
                if extract_path:
                    shutil.rmtree(extract_path, ignore_errors=True)
                await database.disable_token(token_doc["token"])
                await token_manager.release_token(token_doc["token"])
                await client.close()
                continue

        terminal.add_error(f"all tokens exhausted. last error: {last_error}")
        return {"success": False, "error": f"All Railway tokens exhausted. Last error: {last_error}", "deployment_id": deployment_id}

    async def stop_deployment(self, deployment_id: str) -> bool:
        dep = await database.get_deployment(deployment_id)
        if not dep:
            return False
        terminal = self.get_terminal(deployment_id)
        terminal.add_line("stopping deployment...")

        client = RailwayClient(dep["railway_token"])
        try:
            await client.delete_deployment(dep["railway_deployment_id"])
            await database.update_deployment(deployment_id, {"status": "stopped"})
            terminal.add_line("deployment stopped")
            return True
        except Exception as e:
            logger.error(f"Stop error: {e}")
            return False
        finally:
            await client.close()

    async def restart_deployment(self, deployment_id: str) -> bool:
        dep = await database.get_deployment(deployment_id)
        if not dep:
            return False
        terminal = self.get_terminal(deployment_id)
        terminal.add_line("restarting deployment...")

        client = RailwayClient(dep["railway_token"])
        try:
            new_dep_id = await client.create_deployment(dep["service_id"], dep["environment_id"])
            if new_dep_id:
                await database.update_deployment(deployment_id, {
                    "status": "running",
                    "railway_deployment_id": new_dep_id,
                    "restart_count": dep.get("restart_count", 0) + 1
                })
                terminal.add_line(f"deployment restarted: {new_dep_id[:8]}...")
                return True
            return False
        except Exception as e:
            logger.error(f"Restart error: {e}")
            return False
        finally:
            await client.close()

    async def redeploy_deployment(self, deployment_id: str) -> Optional[str]:
        dep = await database.get_deployment(deployment_id)
        if not dep:
            return None
        terminal = self.get_terminal(deployment_id)
        terminal.add_line("triggering repository update & redeploy...")

        client = RailwayClient(dep["railway_token"])
        try:
            new_dep_id = await client.create_deployment(dep["service_id"], dep["environment_id"])
            if new_dep_id:
                await database.update_deployment(deployment_id, {
                    "status": "deploying",
                    "railway_deployment_id": new_dep_id,
                })
                terminal.add_line(f"new deployment triggered: {new_dep_id[:8]}...")
                terminal.add_line("building repository updates...")
                return new_dep_id
            return None
        except Exception as e:
            logger.error(f"Redeploy error: {e}")
            terminal.add_error(f"redeploy failed: {str(e)}")
            return None
        finally:
            await client.close()

    async def delete_deployment(self, deployment_id: str) -> bool:
        dep = await database.get_deployment(deployment_id)
        if not dep:
            return False
        terminal = self.get_terminal(deployment_id)

        client = RailwayClient(dep["railway_token"])
        try:
            await client.delete_project(dep["project_id"])
            await database.delete_deployment(deployment_id)
            await token_manager.release_token(dep["railway_token"])

            # Clean up saved zip backup
            try:
                zip_save_path = os.path.join("data", "zips", f"{deployment_id}.zip")
                if os.path.exists(zip_save_path):
                    os.remove(zip_save_path)
            except Exception as zip_del_err:
                logger.error(f"Failed to delete zip backup: {zip_del_err}")

            terminal.add_line("deployment deleted")
            return True
        except Exception as e:
            logger.error(f"Delete error: {e}")
            return False
        finally:
            await client.close()

    async def migrate_deployment(self, deployment_id: str, new_token: str = None) -> bool:
        dep = await database.get_deployment(deployment_id)
        if not dep:
            return False

        terminal = self.get_terminal(deployment_id)
        terminal.add_line("starting migration...")

        if not new_token:
            token_doc = await token_manager.get_available_token()
            if not token_doc:
                terminal.add_error("no tokens available for migration")
                return False
            new_token = token_doc["token"]
            
        try:
            from bot.services.log_service import owner_log
            await owner_log.send_user_notification(
                dep["user_id"],
                f"🔄 <b>Railway Token Switch Notification</b>\n\n"
                f"Your bot (ID: <code>{deployment_id[:8]}</code>) has been switched to a new Railway API token because the previous token was deactivated or exhausted. "
                f"The bot is now being migrated and redeployed on the new token to maintain continuous operation."
            )
        except Exception as notify_err:
            logger.error(f"Failed to send migration token switch notification: {notify_err}")

        old_token = dep["railway_token"]
        old_client = RailwayClient(old_token)
        new_client = RailwayClient(new_token)

        try:
            project_name = f"pbc-{dep['user_id']}-{int(time.time())}"
            project = await new_client.create_project(project_name)
            project_id = project["projectCreate"]["id"]

            env = await new_client.create_environment(project_id)
            env_id = env["environmentCreate"]["id"]

            is_zip = dep.get("repo_url") == "ZIP Upload"
            
            if is_zip:
                # Local ZIP migration
                zip_save_path = os.path.join("data", "zips", f"{deployment_id}.zip")
                if not os.path.exists(zip_save_path):
                    terminal.add_error("source zip file not found for migration")
                    return False
                    
                with open(zip_save_path, "rb") as f:
                    zip_data = f.read()

                service = await new_client.create_service(project_id, "bot-service")
                service_id = service["serviceCreate"]["id"]
                
                # Check if region is set or fallback
                region_code = dep.get("region", "us-west1")
                await new_client.update_service_instance_region(service_id, env_id, region_code)

                # Set variables
                for key, value in dep.get("variables", {}).items():
                    await new_client.set_environment_variable(project_id, env_id, key, value, service_id=service_id)

                # Extract and deploy using Railway CLI
                extract_path = os.path.join(settings.TEMP_DIR, f"migrate_{deployment_id}")
                os.makedirs(extract_path, exist_ok=True)
                await github_client.extract_zip_to_path(zip_data, extract_path)
                
                cmd = f'railway up --detach --json --project "{project_id}" --service "{service_id}" --environment "{env_id}"'
                env_vars = os.environ.copy()
                env_vars["RAILWAY_TOKEN"] = new_token
                
                proc = await asyncio.create_subprocess_shell(
                    cmd,
                    cwd=extract_path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env_vars
                )
                stdout_bytes, stderr_bytes = await proc.communicate()
                shutil.rmtree(extract_path, ignore_errors=True)
                
                if proc.returncode != 0:
                    err_msg = stderr_bytes.decode("utf-8", errors="ignore")
                    terminal.add_error(f"Railway CLI upload failed during migration: {err_msg}")
                    return False

                # Parse new deployment ID
                import re
                dep_id = None
                try:
                    stdout_str = stdout_bytes.decode("utf-8", errors="ignore")
                    import json
                    try:
                        data = json.loads(stdout_str)
                        dep_id = data.get("deploymentId") or data.get("id")
                    except Exception:
                        match = re.search(r'"(?:deployment)?Id"\s*:\s*"([^"]+)"', stdout_str)
                        if match:
                            dep_id = match.group(1)
                except Exception:
                    pass

                if not dep_id:
                    dep_id = str(uuid.uuid4())[:12]
            else:
                # GitHub migration
                parsed = github_client.parse_github_url(dep["repo_url"])
                if not parsed:
                    terminal.add_error("invalid repository URL in record")
                    return False
                    
                repo_slug = f"{parsed['owner']}/{parsed['repo']}"
                service = await new_client.create_service(project_id, "bot-service", source_repo=repo_slug)
                service_id = service["serviceCreate"]["id"]
                
                # Check if region is set or fallback
                region_code = dep.get("region", "us-west1")
                await new_client.update_service_instance_region(service_id, env_id, region_code)

                # Set variables
                for key, value in dep.get("variables", {}).items():
                    await new_client.set_environment_variable(project_id, env_id, key, value, service_id=service_id)

                dep_id = await new_client.create_deployment(service_id, env_id)
                if not dep_id:
                    terminal.add_error("migration deploy failed")
                    return False

            # Generate public domain automatically
            domain_doc = await new_client.create_service_domain(service_id, env_id)
            if domain_doc and domain_doc.get("domain"):
                dep_url = f"https://{domain_doc['domain']}"
            else:
                dep_url = f"https://{project_id}.up.railway.app"

            try:
                await old_client.delete_project(dep["project_id"])
            except Exception as old_err:
                logger.error(f"Failed to delete old project: {old_err}")

            await token_manager.release_token(old_token)

            await database.update_deployment(deployment_id, {
                "railway_token": new_token,
                "project_id": project_id,
                "environment_id": env_id,
                "service_id": service_id,
                "railway_deployment_id": dep_id,
                "status": "running",
                "url": dep_url,
            })

            terminal.add_line("migration completed successfully")
            return True
        except Exception as e:
            logger.error(f"Migration error: {e}")
            terminal.add_error(f"migration failed: {str(e)}")
            return False
        finally:
            await old_client.close()
            await new_client.close()

    async def get_deployment_logs(self, deployment_id: str) -> str:
        return await self.get_runtime_logs(deployment_id)

    async def get_build_logs(self, deployment_id: str, limit: int = 100) -> str:
        dep = await database.get_deployment(deployment_id)
        if not dep:
            return "Deployment not found"
        client = RailwayClient(dep["railway_token"])
        try:
            logs = await client.get_build_logs(dep["railway_deployment_id"], limit)
            if not logs:
                return "No build logs available yet."
            return "\n".join(f"[{log.get('timestamp', '')}] {log.get('message', '')}" for log in logs)
        except Exception as e:
            return f"Error fetching build logs: {str(e)}"
        finally:
            await client.close()

    async def get_runtime_logs(self, deployment_id: str, limit: int = 100) -> str:
        dep = await database.get_deployment(deployment_id)
        if not dep:
            return "Deployment not found"
        client = RailwayClient(dep["railway_token"])
        try:
            logs = await client.get_runtime_logs(dep["railway_deployment_id"], limit)
            if not logs:
                return "No application logs available yet."
            return "\n".join(f"[{log.get('timestamp', '')}] {log.get('message', '')}" for log in logs)
        except Exception as e:
            return f"Error fetching runtime logs: {str(e)}"
        finally:
            await client.close()

    async def _send_log(self, log_type: str, data: dict):
        try:
            await database.add_log(log_type, data)
            await owner_log.send_log(log_type, **data)
        except Exception as e:
            logger.error(f"Log error: {e}")

    async def get_runtime_stats(self, deployment_id: str) -> dict:
        dep = await database.get_deployment(deployment_id)
        if not dep:
            return {}
        runtime = time.time() - dep.get("created_at", time.time())
        return {
            "status": dep.get("status", "unknown"),
            "uptime": runtime,
            "url": dep.get("url", ""),
            "restart_count": dep.get("restart_count", 0),
            "framework": dep.get("framework", "Unknown"),
            "startup_file": dep.get("startup_file", "Unknown"),
        }


deployment_engine = DeploymentEngine()
