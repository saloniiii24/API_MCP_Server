import json
import time
import re
import requests
from pathlib import Path
from typing import Optional, List
from urllib.parse import urlencode

from models.api_dataset import ApiDataset
from tools.api_variable_tool import ApiVariableService
from tools.api_intelligence_tool import ApiIntelligenceTool
from tools.api_discovery_tool import ApiDiscoveryTool
from tools.api_backup_tool import ApiBackupTool


class ApiExecutionTool:

    def __init__(self, artefacts_base_path: str):
        self.base_path = Path(artefacts_base_path)

        self.discovery = ApiDiscoveryTool(artefacts_base_path)
        self.variables = ApiVariableService(self.discovery)
        self.backup = ApiBackupTool(artefacts_base_path)
        self.intelligence = ApiIntelligenceTool(artefacts_base_path)

        self.timeout = 30

    # =========================================================
    def execute_api(
        self,
        project_name: str,
        collection_id: str,
        endpoint_id: str,
        dataset_id: str,
        base_url_override: Optional[str] = None,
        auto_heal: bool = False,
        analyze_flows: bool = False,
        capture_response: bool = False,
        alternate_path: Optional[str] = None
    ):
        alt = Path(alternate_path) if alternate_path else None

        base_dir = (
            alt / "collections" / collection_id
            if alt else
            self.base_path / "Main" / project_name / "api_discovery" / "collections" / collection_id
        )

        # ===== Load collection =====
        collection = json.loads((base_dir / "collection.json").read_text())

        # ===== Load dataset =====
        ds_file = base_dir / "datasets" / f"{endpoint_id}.json"
        if ds_file.exists():
            datasets = [ApiDataset.from_dict(d) for d in json.loads(ds_file.read_text())]
        else:
            datasets = [ApiDataset()]

        dataset = next(
            (d for d in datasets if d.id == dataset_id or dataset_id == "active"),
            None
        )
        if not dataset:
            raise Exception(f"Dataset not found: {dataset_id}")

        # ===== Find endpoint =====
        endpoint = None
        for g in collection.get("groups", []):
            for ep in g.get("endpoints", []):
                if ep["id"] == endpoint_id:
                    endpoint = ep
                    break

        if not endpoint:
            raise Exception("Endpoint not found")

        # ===== Variable substitution =====
        if not alt:
            dataset = self.variables.substitute_variables(project_name, collection_id, dataset.to_dict())
            dataset = ApiDataset.from_dict(dataset)

        # ===== Base URL =====
        base_url = base_url_override or dataset.baseUrl or "http://localhost:8080"
        base_url = base_url.rstrip("/")

        # ===== Path =====
        path = endpoint["path"]

        for k, v in dataset.pathParams.items():
            path = path.replace(f"{{{k}}}", str(v))

        if re.search(r"{.*}", path):
            raise Exception("Missing path params")

        if dataset.queryParams:
            path += "?" + urlencode(dataset.queryParams)

        if not path.startswith("/"):
            path = "/" + path

        url = base_url + path

        # ===== Headers =====
        headers = {"Content-Type": endpoint.get("contentType", "application/json")}
        headers.update(dataset.headers)

        # ===== Body =====
        method = endpoint["method"].upper()
        body = None

        if method in ["POST", "PUT", "PATCH"]:
            body = dataset.body

        # ===== Execute =====
        start = time.time()

        response = requests.request(
            method=method,
            url=url,
            headers=headers,
            json=body if isinstance(body, dict) else None,
            timeout=self.timeout
        )

        duration = int((time.time() - start) * 1000)

        result = {
            "statusCode": response.status_code,
            "duration": duration,
            "body": response.text,
            "headers": dict(response.headers)
        }

        # ===== Capture response =====
        if capture_response:
            resp_dir = base_dir / "responses"
            resp_dir.mkdir(exist_ok=True)

            file_name = f"resp_{endpoint_id}_{dataset.id}.json"

            with open(resp_dir / file_name, "w") as f:
                json.dump(result, f, indent=2)

            dataset.lastResponseFile = file_name
            dataset.lastStatusCode = response.status_code

            with open(ds_file, "w") as f:
                json.dump([d.to_dict() for d in datasets], f, indent=2)

        return result


def init_execution_tool(path: str):
    return ApiExecutionTool(path)