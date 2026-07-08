import asyncio
import json
import logging
import time
from typing import Optional

import aiohttp
from bot.config.settings import settings

logger = logging.getLogger(__name__)


class RailwayClient:
    API_BASE = "https://backboard.railway.app/graphql/v2"

    def __init__(self, token: str):
        self.token = token
        self.session: Optional[aiohttp.ClientSession] = None
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "User-Agent": "PythonBotCloud/7.0",
        }

    async def ensure_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(headers=self.headers)

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()

    async def _query(self, query: str, variables: dict = None) -> dict:
        await self.ensure_session()
        payload = {"query": query}
        if variables:
            payload["variables"] = variables
        try:
            async with self.session.post(self.API_BASE, json=payload) as resp:
                if resp.status == 401:
                    raise PermissionError("Invalid Railway token")
                data = await resp.json()
                if "errors" in data:
                    raise Exception(f"GraphQL error: {data['errors']}")
                return data.get("data", {})
        except aiohttp.ClientError as e:
            logger.error(f"Railway API request failed: {e}")
            raise

    async def validate_token(self) -> bool:
        query = """
        query {
            me {
                id
                email
            }
        }
        """
        try:
            result = await self._query(query)
            return bool(result.get("me", {}).get("id"))
        except Exception:
            return False

    async def get_account_info(self) -> dict:
        query = """
        query {
            me {
                id
                email
                name
            }
        }
        """
        return await self._query(query)

    async def create_project(self, name: str) -> Optional[dict]:
        workspace_query = """
        query {
            me {
                workspaces {
                    id
                }
            }
        }
        """
        try:
            me_data = await self._query(workspace_query)
            workspaces = me_data.get("me", {}).get("workspaces", [])
            if not workspaces:
                logger.error("No workspaces found for user")
                return None
            workspace_id = workspaces[0]["id"]
            
            query = """
            mutation CreateProject($input: ProjectCreateInput!) {
                projectCreate(input: $input) {
                    id
                    name
                }
            }
            """
            variables = {"input": {"name": name, "workspaceId": workspace_id}}
            return await self._query(query, variables)
        except Exception as e:
            logger.error(f"Failed to create project: {e}")
            raise

    async def create_environment(self, project_id: str, name: str = "production") -> Optional[dict]:
        fetch_query = """
        query FetchProject($id: String!) {
            project(id: $id) {
                environments {
                    edges {
                        node {
                            id
                            name
                        }
                    }
                }
            }
        }
        """
        try:
            res = await self._query(fetch_query, {"id": project_id})
            envs = res.get("project", {}).get("environments", {}).get("edges", [])
            for edge in envs:
                if edge["node"]["name"] == name:
                    return {"environmentCreate": {"id": edge["node"]["id"], "name": name}}
            if envs:
                return {"environmentCreate": {"id": envs[0]["node"]["id"], "name": envs[0]["node"]["name"]}}
        except Exception as e:
            logger.error(f"Failed to fetch existing environment: {e}")

        query = """
        mutation CreateEnvironment($input: EnvironmentCreateInput!) {
            environmentCreate(input: $input) {
                id
                name
            }
        }
        """
        variables = {"input": {"projectId": project_id, "name": name}}
        try:
            return await self._query(query, variables)
        except Exception as e:
            logger.error(f"Failed to create environment: {e}")
            return None

    async def create_service(self, project_id: str, name: str, source_repo: str = None) -> Optional[dict]:
        query = """
        mutation CreateService($input: ServiceCreateInput!) {
            serviceCreate(input: $input) {
                id
                name
            }
        }
        """
        input_data = {"projectId": project_id, "name": name}
        if source_repo:
            input_data["source"] = {"repo": source_repo}
        variables = {"input": input_data}
        try:
            return await self._query(query, variables)
        except Exception as e:
            logger.error(f"Failed to create service: {e}")
            return None

    async def create_deployment(self, service_id: str, environment_id: str) -> Optional[str]:
        query = """
        mutation CreateDeployment($serviceId: String!, $environmentId: String!) {
            serviceInstanceDeployV2(serviceId: $serviceId, environmentId: $environmentId)
        }
        """
        variables = {"serviceId": service_id, "environmentId": environment_id}
        try:
            res = await self._query(query, variables)
            return res.get("serviceInstanceDeployV2")
        except Exception as e:
            logger.error(f"Failed to create deployment: {e}")
            return None

    async def trigger_deploy(self, service_id: str, environment_id: str) -> bool:
        query = """
        mutation Deploy($serviceId: String!, $environmentId: String!) {
            serviceInstanceRedeploy(serviceId: $serviceId, environmentId: $environmentId)
        }
        """
        variables = {"serviceId": service_id, "environmentId": environment_id}
        try:
            res = await self._query(query, variables)
            return bool(res.get("serviceInstanceRedeploy"))
        except Exception as e:
            logger.error(f"Failed to trigger deploy: {e}")
            return False

    async def get_deployment(self, deployment_id: str) -> Optional[dict]:
        query = """
        query GetDeployment($id: String!) {
            deployment(id: $id) {
                id
                status
                url
                createdAt
                staticUrl
                canRedeploy
            }
        }
        """
        variables = {"id": deployment_id}
        try:
            return await self._query(query, variables)
        except Exception as e:
            logger.error(f"Failed to get deployment: {e}")
            return None

    async def get_deployment_logs(self, deployment_id: str) -> list:
        return await self.get_runtime_logs(deployment_id)

    async def get_build_logs(self, deployment_id: str, limit: int = 100) -> list:
        query = """
        query GetBuildLogs($deploymentId: String!, $limit: Int) {
            buildLogs(deploymentId: $deploymentId, limit: $limit) {
                timestamp
                message
                severity
            }
        }
        """
        variables = {"deploymentId": deployment_id, "limit": limit}
        try:
            result = await self._query(query, variables)
            return result.get("buildLogs", [])
        except Exception as e:
            logger.error(f"Failed to get build logs: {e}")
            return []

    async def get_runtime_logs(self, deployment_id: str, limit: int = 100) -> list:
        query = """
        query GetRuntimeLogs($deploymentId: String!, $limit: Int) {
            deploymentLogs(deploymentId: $deploymentId, limit: $limit) {
                timestamp
                message
                severity
            }
        }
        """
        variables = {"deploymentId": deployment_id, "limit": limit}
        try:
            result = await self._query(query, variables)
            return result.get("deploymentLogs", [])
        except Exception as e:
            logger.error(f"Failed to get runtime logs: {e}")
            return []

    async def get_regions(self) -> list:
        query = """
        query {
            regions {
                name
                country
                location
            }
        }
        """
        try:
            result = await self._query(query)
            return result.get("regions", [])
        except Exception as e:
            logger.error(f"Failed to get regions: {e}")
            return []

    async def update_service_instance_region(self, service_id: str, environment_id: str, region: str) -> bool:
        query = """
        mutation UpdateServiceInstance($serviceId: String!, $environmentId: String!, $input: ServiceInstanceUpdateInput!) {
            serviceInstanceUpdate(serviceId: $serviceId, environmentId: $environmentId, input: $input)
        }
        """
        variables = {
            "serviceId": service_id,
            "environmentId": environment_id,
            "input": {
                "region": region
            }
        }
        try:
            result = await self._query(query, variables)
            return bool(result.get("serviceInstanceUpdate"))
        except Exception as e:
            logger.error(f"Failed to update service instance region: {e}")
            return False

    async def create_service_domain(self, service_id: str, environment_id: str) -> Optional[dict]:
        query = """
        mutation CreateServiceDomain($input: ServiceDomainCreateInput!) {
            serviceDomainCreate(input: $input) {
                id
                domain
            }
        }
        """
        variables = {
            "input": {
                "serviceId": service_id,
                "environmentId": environment_id
            }
        }
        try:
            result = await self._query(query, variables)
            return result.get("serviceDomainCreate")
        except Exception as e:
            logger.error(f"Failed to create service domain: {e}")
            return None

    async def create_custom_domain(self, project_id: str, environment_id: str, service_id: str, domain: str) -> Optional[dict]:
        query = """
        mutation CreateCustomDomain($input: CustomDomainCreateInput!) {
            customDomainCreate(input: $input) {
                id
                domain
            }
        }
        """
        variables = {
            "input": {
                "projectId": project_id,
                "environmentId": environment_id,
                "serviceId": service_id,
                "domain": domain
            }
        }
        try:
            result = await self._query(query, variables)
            return result.get("customDomainCreate")
        except Exception as e:
            logger.error(f"Failed to create custom domain: {e}")
            return None

    async def get_service_domains(self, project_id: str, environment_id: str, service_id: str) -> dict:
        query = """
        query GetDomains($projectId: String!, $environmentId: String!, $serviceId: String!) {
            domains(projectId: $projectId, environmentId: $environmentId, serviceId: $serviceId) {
                serviceDomains {
                    id
                    domain
                }
                customDomains {
                    id
                    domain
                }
            }
        }
        """
        variables = {
            "projectId": project_id,
            "environmentId": environment_id,
            "serviceId": service_id
        }
        try:
            result = await self._query(query, variables)
            return result.get("domains", {})
        except Exception as e:
            logger.error(f"Failed to get service domains: {e}")
            return {}

    async def delete_service_domain(self, domain_id: str) -> bool:
        query = """
        mutation DeleteServiceDomain($id: String!) {
            serviceDomainDelete(id: $id)
        }
        """
        variables = {"id": domain_id}
        try:
            result = await self._query(query, variables)
            return bool(result.get("serviceDomainDelete"))
        except Exception as e:
            logger.error(f"Failed to delete service domain: {e}")
            return False

    async def delete_deployment(self, deployment_id: str) -> bool:
        query = """
        mutation DeleteDeployment($id: String!) {
            deploymentDelete(id: $id) {
                id
            }
        }
        """
        variables = {"id": deployment_id}
        try:
            await self._query(query, variables)
            return True
        except Exception as e:
            logger.error(f"Failed to delete deployment: {e}")
            return False

    async def get_environment_variables(self, project_id: str, environment_id: str) -> list:
        query = """
        query GetVariables($projectId: String!, $environmentId: String!) {
            environment(projectId: $projectId, id: $environmentId) {
                variables {
                    ... on Variable {
                        id
                        name
                        value
                    }
                }
            }
        }
        """
        variables = {"projectId": project_id, "environmentId": environment_id}
        try:
            result = await self._query(query, variables)
            return result.get("environment", {}).get("variables", [])
        except Exception:
            return []

    async def set_environment_variable(self, project_id: str, environment_id: str, name: str, value: str, service_id: str = None) -> bool:
        query = """
        mutation SetVariable($input: VariableUpsertInput!) {
            variableUpsert(input: $input)
        }
        """
        input_data = {
            "projectId": project_id,
            "environmentId": environment_id,
            "name": name,
            "value": value
        }
        if service_id:
            input_data["serviceId"] = service_id
        variables = {"input": input_data}
        try:
            res = await self._query(query, variables)
            return bool(res.get("variableUpsert"))
        except Exception as e:
            logger.error(f"Failed to set variable: {e}")
            return False

    async def delete_environment_variable(self, project_id: str, environment_id: str, name: str, service_id: str = None) -> bool:
        query = """
        mutation DeleteVariable($input: VariableDeleteInput!) {
            variableDelete(input: $input)
        }
        """
        input_data = {
            "projectId": project_id,
            "environmentId": environment_id,
            "name": name
        }
        if service_id:
            input_data["serviceId"] = service_id
        variables = {"input": input_data}
        try:
            res = await self._query(query, variables)
            return bool(res.get("variableDelete"))
        except Exception as e:
            logger.error(f"Failed to delete variable: {e}")
            return False

    async def get_project_usage(self, project_id: str) -> dict:
        query = """
        query GetUsage($projectId: String!) {
            project(id: $projectId) {
                usage {
                    cpu
                    memory
                    network
                }
            }
        }
        """
        variables = {"projectId": project_id}
        try:
            return await self._query(query, variables)
        except Exception:
            return {}

    async def delete_project(self, project_id: str) -> bool:
        query = """
        mutation DeleteProject($id: String!) {
            deleteProject(id: $id) {
                id
            }
        }
        """
        variables = {"id": project_id}
        try:
            await self._query(query, variables)
            return True
        except Exception as e:
            logger.error(f"Failed to delete project: {e}")
            return False
