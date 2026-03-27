import json
import shutil
from pathlib import Path
from typing import List, Dict
from collections import defaultdict
from datetime import datetime
from tools.llm_service import LLMService


class ApiDiscoveryTool:

    def __init__(self, artefacts_base_path: str):
        self.artefacts_base_path = artefacts_base_path
        self.llm_tool = LLMService()
        self.discovery_status: Dict[str, str] = {}

    # =========================================================
    # ENTRY POINT
    # =========================================================
    def discover_apis(self, project_name: str, input_type: str, file_path: str):

        file_path = Path(file_path)

        if input_type == "swagger":
            return self._discover_from_swagger(project_name, file_path)

        elif input_type == "postman":
            return self._discover_from_postman(project_name, file_path)

        elif input_type == "curl":
            return self._discover_from_curl(project_name, file_path)

        else:
            raise Exception(f"Unsupported input type: {input_type}")

    # =========================================================
    # SWAGGER
    # =========================================================
    def _discover_from_swagger(self, project_name: str, swagger_file: Path):

        self.discovery_status[project_name] = "RUNNING"

        with open(swagger_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        endpoints = []

        for path, methods in data.get("paths", {}).items():
            for method, operation in methods.items():

                method = method.upper()
                if method not in ["GET", "POST", "PUT", "DELETE", "PATCH"]:
                    continue

                ep = {
                    "id": str(datetime.now().timestamp()).replace(".", ""),
                    "method": method,
                    "path": path,
                    "summary": operation.get("summary", ""),
                    "headers": [],
                    "parameters": operation.get("parameters", []),
                    "requestBodySchema": operation.get("requestBody"),
                    "responseBodySchema": self._extract_success_response(operation),
                    "sourceFile": (operation.get("tags") or ["General"])[0],
                }

                endpoints.append(ep)

        dependencies = self._discover_dependencies(endpoints)

        collection_id = self._save_collection(
            project_name, endpoints, dependencies, swagger_file, "swagger.json"
        )

        self.discovery_status[project_name] = "COMPLETED"

        return {
            "collectionId": collection_id,
            "endpoints": len(endpoints),
            "dependencies": len(dependencies),
        }

    # =========================================================
    # POSTMAN
    # =========================================================
    def _discover_from_postman(self, project_name: str, postman_file: Path):

        with open(postman_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        endpoints = []

        def parse_items(items):
            for item in items:
                if "item" in item:
                    parse_items(item["item"])
                else:
                    req = item.get("request", {})

                    ep = {
                        "id": str(datetime.now().timestamp()).replace(".", ""),
                        "method": req.get("method", "GET"),
                        "path": req.get("url", {}).get("raw", ""),
                        "summary": item.get("name", ""),
                        "headers": req.get("header", []),
                        "requestBodySchema": req.get("body", {}),
                        "sourceFile": "Postman",
                    }

                    endpoints.append(ep)

        parse_items(data.get("item", []))

        dependencies = self._discover_dependencies(endpoints)

        collection_id = self._save_collection(
            project_name, endpoints, dependencies, postman_file, "postman.json"
        )

        return {"collectionId": collection_id}

    # =========================================================
    # CURL
    # =========================================================
    def _discover_from_curl(self, project_name: str, curl_file: Path):

        with open(curl_file, "r") as f:
            lines = f.readlines()

        endpoints = []

        for line in lines:
            if not line.strip().startswith("curl"):
                continue

            prompt = f"Convert CURL to JSON:\n{line}"

            try:
                raw = self.llm_tool.generate(prompt)
                parsed = json.loads(self._clean_json_object(raw))

                ep = {
                    "id": str(datetime.now().timestamp()).replace(".", ""),
                    "method": parsed.get("method"),
                    "path": parsed.get("path"),
                    "headers": parsed.get("headers", []),
                    "requestBodySchema": parsed.get("body"),
                    "sourceFile": "CURL",
                }

                endpoints.append(ep)

            except Exception:
                continue

        dependencies = self._discover_dependencies(endpoints)

        collection_id = self._save_collection(
            project_name, endpoints, dependencies, curl_file, "curl.txt"
        )

        return {"collectionId": collection_id}

    # =========================================================
    # DEPENDENCIES (AI + BASIC)
    # =========================================================
    def _discover_dependencies(self, endpoints):

        if not endpoints:
            return []

        prompt = "\n".join([f"{e['method']} {e['path']}" for e in endpoints])

        try:
            raw = self.llm_tool.generate(f"Find API dependencies:\n{prompt}")
            parsed = json.loads(self._clean_json_array(raw))
            return parsed
        except Exception:
            return []

    # =========================================================
    # SAVE COLLECTION
    # =========================================================
    def _save_collection(self, project, endpoints, dependencies, source_file, source_name):

        collection_id = f"collection_{int(datetime.now().timestamp())}"

        collection = {
            "id": collection_id,
            "groups": self._group_endpoints(endpoints),
            "dependencies": dependencies,
            "variables": {},
        }

        base = Path(self.artefacts_base_path) / "Main" / project / "api_discovery" / "collections"
        base.mkdir(parents=True, exist_ok=True)

        col_dir = base / collection_id
        col_dir.mkdir(exist_ok=True)

        # Save collection
        with open(col_dir / "collection.json", "w") as f:
            json.dump(collection, f, indent=2)

        # ✅ CREATE DEFAULT DATASETS (THIS WAS MISSING)
        datasets_dir = col_dir / "datasets"
        datasets_dir.mkdir(exist_ok=True)

        for ep in endpoints:
            dataset = {
                "id": "default",
                "baseUrl": "",
                "headers": {},
                "queryParams": {},
                "pathParams": {},
                "body": {},
                "formParams": {},
                "captures": []
            }

            with open(datasets_dir / f"{ep['id']}.json", "w") as f:
                json.dump([dataset], f, indent=2)

        if source_file.exists():
            shutil.copy(source_file, col_dir / source_name)

        return collection_id

    def _group_endpoints(self, endpoints):

        groups = defaultdict(list)

        for ep in endpoints:
            groups[ep.get("sourceFile", "General")].append(ep)

        return [
            {"name": name, "endpoints": eps}
            for name, eps in groups.items()
        ]

    # =========================================================
    # HELPERS
    # =========================================================
    def _extract_success_response(self, operation):

        responses = operation.get("responses", {})
        for code, resp in responses.items():
            if str(code).startswith("2"):
                return resp
        return None

    def _clean_json_array(self, text):
        start = text.find("[")
        end = text.rfind("]")
        return text[start:end + 1] if start != -1 else "[]"

    def _clean_json_object(self, text):
        start = text.find("{")
        end = text.rfind("}")
        return text[start:end + 1] if start != -1 else "{}"

    # =========================================================
    # LOAD COLLECTION
    # =========================================================
    def get_collection(self, project_name: str, collection_id: str):

        path = (
            Path(self.artefacts_base_path)
            / "Main"
            / project_name
            / "api_discovery"
            / "collections"
            / collection_id
            / "collection.json"
        )

        if not path.exists():
            raise Exception(f"Collection not found: {path}")

        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)


    # =========================================================
    # LOAD DATASETS
    # =========================================================
    def get_datasets(self, project_name: str, collection_id: str, endpoint_id: str):

        path = (
            Path(self.artefacts_base_path)
            / "Main"
            / project_name
            / "api_discovery"
            / "collections"
            / collection_id
            / "datasets"
            / f"{endpoint_id}.json"
        )

        if not path.exists():
            return []

        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)


    # =========================================================
    # SAVE COLLECTION
    # =========================================================
    def save_collection(self, project_name: str, collection: dict):

        collection_id = collection.get("id")

        path = (
            Path(self.artefacts_base_path)
            / "Main"
            / project_name
            / "api_discovery"
            / "collections"
            / collection_id
            / "collection.json"
        )

        with open(path, "w", encoding="utf-8") as f:
            json.dump(collection, f, indent=2)


# =========================================================
# MCP INIT (IMPORTANT)
# =========================================================
def init_discovery_tool(artefacts_base_path: str):
    return ApiDiscoveryTool(artefacts_base_path)