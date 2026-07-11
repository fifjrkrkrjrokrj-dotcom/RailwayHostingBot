import asyncio
import io
import logging
import os
import re
import zipfile
from typing import Optional

import aiohttp
from bot.config.settings import settings

logger = logging.getLogger(__name__)

# Timeouts
_DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=30)
_DOWNLOAD_TIMEOUT = aiohttp.ClientTimeout(total=120)  # ZIP can be large


class GitHubClient:
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "PythonBotCloud/7.0",
        }
        if settings.GITHUB_TOKEN and settings.GITHUB_TOKEN != "your_github_token_optional" and "dummy" not in settings.GITHUB_TOKEN.lower():
            self.headers["Authorization"] = f"token {settings.GITHUB_TOKEN}"

    async def ensure_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                headers=self.headers,
                timeout=_DEFAULT_TIMEOUT,
            )

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()

    def parse_github_url(self, url: str) -> Optional[dict]:
        pattern = r"(?:https?://)?(?:www\.)?github\.com/([^/]+)/([^/]+?)(?:\.git)?(?:/tree/([^/]+))?(?:/blob/([^/]+)/(.+))?$"
        match = re.match(pattern, url.strip().rstrip("/"))
        if not match:
            return None
        owner, repo = match.group(1), match.group(2).replace(".git", "")
        branch = match.group(3) or None  # None = auto-detect main/master
        return {"owner": owner, "repo": repo, "branch": branch}

    async def get_repo_info(self, owner: str, repo: str) -> Optional[dict]:
        await self.ensure_session()
        url = f"https://api.github.com/repos/{owner}/{repo}"
        try:
            async with self.session.get(url, timeout=_DEFAULT_TIMEOUT) as resp:
                if resp.status == 200:
                    return await resp.json()
                elif resp.status in (403, 429):
                    # Rate limited or forbidden
                    logger.warning(f"GitHub API rate limited ({resp.status}) for {owner}/{repo}")
                    return {"_rate_limited": True, "_status": resp.status}
                elif resp.status == 404:
                    logger.warning(f"GitHub repo not found: {owner}/{repo}")
                    return {"_not_found": True}
                else:
                    logger.error(f"GitHub API returned HTTP {resp.status} for {owner}/{repo}")
                    return {"_error": True, "_status": resp.status}
        except asyncio.TimeoutError:
            logger.error(f"GitHub API timeout fetching repo info for {owner}/{repo}")
            return {"_timeout": True}
        except Exception as e:
            logger.error(f"GitHub API error: {e}")
            return None

    async def download_repo_zip(self, owner: str, repo: str, branch: str = "main") -> Optional[bytes]:
        await self.ensure_session()
        url = f"https://api.github.com/repos/{owner}/{repo}/zipball/{branch}"
        try:
            async with self.session.get(url, timeout=_DOWNLOAD_TIMEOUT) as resp:
                if resp.status == 200:
                    return await resp.read()
                logger.error(f"Failed to download repo: {resp.status}")
                return None
        except asyncio.TimeoutError:
            logger.error(f"Timeout downloading repo ZIP for {owner}/{repo}@{branch}")
            return None
        except Exception as e:
            logger.error(f"Download error: {e}")
            return None

    async def list_repo_contents(self, owner: str, repo: str, path: str = "", branch: str = "main") -> list:
        await self.ensure_session()
        url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}?ref={branch}"
        try:
            async with self.session.get(url, timeout=_DEFAULT_TIMEOUT) as resp:
                if resp.status == 200:
                    return await resp.json()
                return []
        except asyncio.TimeoutError:
            logger.error(f"Timeout listing repo contents {owner}/{repo}")
            return []
        except Exception:
            return []

    async def get_file_content(self, owner: str, repo: str, path: str, branch: str = "main") -> Optional[str]:
        await self.ensure_session()
        url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}?ref={branch}"
        try:
            async with self.session.get(url, timeout=_DEFAULT_TIMEOUT) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("encoding") == "base64":
                        import base64
                        return base64.b64decode(data["content"]).decode("utf-8")
                return None
        except asyncio.TimeoutError:
            logger.error(f"Timeout getting file content {owner}/{repo}/{path}")
            return None
        except Exception as e:
            logger.error(f"Failed to get file content: {e}")
            return None

    async def _resolve_branch(self, owner: str, repo: str, branch: Optional[str], info: dict) -> str:
        """
        Resolve the correct branch name.
        - If explicitly given in URL → use it directly.
        - Otherwise → use repo's default_branch from API info.
        - Fallback: try 'main', then 'master'.
        """
        if branch:
            return branch
        default = info.get("default_branch")
        if default:
            return default
        # Final fallback
        return "main"

    async def scan_repository(self, owner: str, repo: str, branch: Optional[str] = None) -> dict:
        info = await self.get_repo_info(owner, repo)
        if not info:
            return {"success": False, "error": "Repository not found or GitHub API timeout. Please try again."}

        # Handle specific error cases from get_repo_info
        if info.get("_rate_limited"):
            return {
                "success": False,
                "error": "GitHub API rate limit reached (too many requests). "
                          "Please set a GITHUB_TOKEN in bot config to increase limits, or try again in 1 hour."
            }
        if info.get("_timeout"):
            return {"success": False, "error": "GitHub API timed out. Please try again in a moment."}
        if info.get("_not_found"):
            return {"success": False, "error": f"Repository '{owner}/{repo}' not found. Make sure the URL is correct and the repo is public."}
        if info.get("_error"):
            return {"success": False, "error": f"GitHub API error (HTTP {info.get('_status', '?')}). Please try again."}

        if info.get("private"):
            return {"success": False, "error": "Private repositories not supported. Please make the repo public first."}

        resolved_branch = await self._resolve_branch(owner, repo, branch, info)

        try:
            zip_data = await self.download_repo_zip(owner, repo, resolved_branch)

            # If resolved branch failed and we auto-detected, try the other common branch
            if not zip_data and not branch:
                fallback = "master" if resolved_branch == "main" else "main"
                logger.warning(f"Branch '{resolved_branch}' download failed, trying '{fallback}'")
                zip_data = await self.download_repo_zip(owner, repo, fallback)
                if zip_data:
                    resolved_branch = fallback

            if not zip_data:
                return {"success": False, "error": f"Failed to download repository (branch: {resolved_branch}). The repo may be empty or the branch may not exist."}

            return await self._scan_zip_data(zip_data, owner, repo, resolved_branch)
        except asyncio.TimeoutError:
            logger.exception(f"Scan timeout for {owner}/{repo}")
            return {"success": False, "error": "Repository scan timed out. Please try again with a smaller repo."}
        except Exception as e:
            logger.exception(f"Scan error: {e}")
            return {"success": False, "error": str(e)}

    async def _scan_zip_data(self, zip_data: bytes, owner: str, repo: str, branch: str) -> dict:
        files = []
        contents = {}

        try:
            with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    path = "/".join(info.filename.split("/")[1:])
                    if not path:
                        continue
                    files.append(path)
                    try:
                        contents[path] = zf.read(info).decode("utf-8", errors="ignore")
                    except Exception:
                        contents[path] = ""
        except Exception as e:
            return {"success": False, "error": f"ZIP extraction error: {e}"}

        from bot.utils.formatters import detect_framework, detect_startup_file, is_python_project

        if not is_python_project(files):
            return {"success": False, "error": "Not a Python project. Only Python Telegram bots supported."}

        startup_file = detect_startup_file(files)
        framework = detect_framework(list(contents.values()))

        has_requirements = "requirements.txt" in files
        has_runtime = "runtime.txt" in files
        has_procfile = "Procfile" in files
        has_dockerfile = "Dockerfile" in files
        has_env_example = ".env.example" in files

        requirements_content = contents.get("requirements.txt", "")
        runtime_content = contents.get("runtime.txt", "")

        return {
            "success": True,
            "owner": owner,
            "repo": repo,
            "branch": branch,
            "files": files,
            "contents": contents,
            "startup_file": startup_file,
            "framework": framework,
            "has_requirements": has_requirements,
            "has_runtime": has_runtime,
            "has_procfile": has_procfile,
            "has_dockerfile": has_dockerfile,
            "has_env_example": has_env_example,
            "requirements": requirements_content,
            "runtime": runtime_content,
            "zip_data": zip_data,
        }

    async def extract_zip_to_path(self, zip_data: bytes, extract_path: str) -> list:
        extracted = []
        with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                path = "/".join(info.filename.split("/")[1:])
                if not path:
                    continue
                target = os.path.join(extract_path, path)
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with open(target, "wb") as f:
                    f.write(zf.read(info))
                extracted.append(path)
        return extracted


github_client = GitHubClient()
