import json
import re
from typing import Dict, Any
from tools.api_discovery_tool import ApiDiscoveryTool


class ApiVariableService:

    def __init__(self, api_discovery_service: ApiDiscoveryTool):
        self.api_discovery_service = api_discovery_service

    # =========================================================
    # SUBSTITUTE VARIABLES
    # =========================================================
    def substitute_variables(
        self,
        project_name: str,
        collection_id: str,
        original_dataset
    ):

        collection = self.api_discovery_service.get_collection(
            project_name, collection_id
        )

        if not collection:
            return original_dataset

        # ✅ HANDLE BOTH dict + object
        if isinstance(collection, dict):
            variables: Dict[str, Any] = collection.get("variables", {})
        else:
            variables: Dict[str, Any] = getattr(collection, "variables", {}) or {}

        if not variables:
            return original_dataset

        # ✅ HANDLE BOTH dict + object dataset
        if hasattr(original_dataset, "to_dict"):
            dataset_dict = original_dataset.to_dict()
        else:
            dataset_dict = original_dataset

        dataset_json = json.dumps(dataset_dict)

        pattern = re.compile(r"\{\{([^}]+)}}")

        def replace(match):
            var_name = match.group(1).strip()
            return str(variables.get(var_name, match.group(0)))

        updated_json = pattern.sub(replace, dataset_json)

        return json.loads(updated_json)

    # =========================================================
    # EXTRACT VARIABLES FROM RESPONSE
    # =========================================================
    def extract_variables(
        self,
        project_name: str,
        collection_id: str,
        response_body: str,
        dataset
    ):

        # ✅ HANDLE BOTH dict + object dataset
        captures = dataset.get("captures") if isinstance(dataset, dict) else getattr(dataset, "captures", [])

        if not captures:
            return

        try:
            root_node = json.loads(response_body)
        except Exception:
            print("Cannot extract variables: Response is not valid JSON.")
            return

        collection = self.api_discovery_service.get_collection(
            project_name, collection_id
        )

        if not collection:
            return

        # ✅ HANDLE dict vs object
        if isinstance(collection, dict):
            variables = collection.setdefault("variables", {})
        else:
            if getattr(collection, "variables", None) is None:
                collection.variables = {}
            variables = collection.variables

        updated = False

        for capture in captures:

            # ✅ handle dict vs object
            if isinstance(capture, dict):
                json_path = capture.get("jsonPath")
                var_name = capture.get("variableName")
            else:
                json_path = capture.jsonPath
                var_name = capture.variableName

            if not json_path or not var_name:
                continue

            value = self._extract_value_by_path(root_node, json_path)

            if value is not None:
                variables[var_name] = value
                updated = True
                print(f"Captured variable: {var_name} = {value}")

        if updated:
            self.api_discovery_service.save_collection(project_name, collection)

    # =========================================================
    # JSON PATH EXTRACTION
    # =========================================================
    def _extract_value_by_path(self, data: Dict, path: str):

        if path.startswith("$."):
            path = path[2:]

        parts = path.split(".")
        current = data

        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None

        return str(current) if current is not None else None