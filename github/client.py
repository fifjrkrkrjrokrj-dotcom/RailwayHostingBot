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
            self.session = aiohttp.ClientSession(headers=self.headers)

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()

    def parse_github_url(self, url: str) -> Optional[dict]:
        pattern = r"(?:https?://)?(?:www\.)?github\.com/([^/]+)/([^/]+?)(?:\.git)?(?:/tree/([^/]+))?(?:/blob/([^/]+)/(.+))?$"
        match = re.match(pattern, url.strip().rstrip("/"))
        if not match:
            return None
        owner, repo = match.group(1), match.group(2).replace(".git", "")
        branch = match.group(3) or "main"
        return {"owner": owner, "repo": repo, "branch": branch}

    async def get_repo_info(self, owner: str, repo: str) -> Optional[dict]:
        await self.ensure_session()
        url = f"https://api.github.com/repos/{owner}/{repo}"
        try:
            async with self.session.get(url) as resp:
                if resp.status == 200:
                    return await resp.json()
                return None
        except Exception as e:
            logger.error(f"GitHub API error: {e}")
            return None

    async def download_repo_zip(self, owner: str, repo: str, branch: str = "main") -> Optional[bytes]:
        await self.ensure_session()
        url = f"https://api.github.com/repos/{owner}/{repo}/zipball/{branch}"
        try:
            async with self.session.get(url) as resp:
                if resp.status == 200:
                    return await resp.read()
                logger.error(f"Failed to download repo: {resp.status}")
                return None
        except Exception as e:
            logger.error(f"Download error: {e}")
            return None

    async def list_repo_contents(self, owner: str, repo: str, path: str = "", branch: str = "main") -> list:
        await self.ensure_session()
        url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}?ref={branch}"
        try:
            async with self.session.get(url) as resp:
                if resp.status == 200:
                    return await resp.json()
                return []
        except Exception:
            return []

    async def get_file_content(self, owner: str, repo: str, path: str, branch: str = "main") -> Optional[str]:
        await self.ensure_session()
        url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}?ref={branch}"
        try:
            async with self.session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("encoding") == "base64":
                        import base64
                        return base64.b64decode(data["content"]).decode("utf-8")
                return None
        except Exception as e:
            logger.error(f"Failed to get file content: {e}")
            return None

    async def scan_repository(self, owner: str, repo: str, branch: str = "main") -> dict:
        info = await self.get_repo_info(owner, repo)
        if not info:
            return {"success": False, "error": "Repository not found"}

        if info.get("private"):
            return {"success": False, "error": "Private repositories not supported"}

        try:
            zip_data = await self.download_repo_zip(owner, repo, branch)
            if not zip_data:
                return {"success": False, "error": "Failed to download repository"}
            return await self._scan_zip_data(zip_data, owner, repo, branch)
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
