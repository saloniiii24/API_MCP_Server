from typing import Dict, List, Any
from models.api_capture import ApiCapture


class ApiDataset:
    def __init__(
        self,
        id: str = "default",
        baseUrl: str = "",
        headers: Dict[str, Any] = None,
        queryParams: Dict[str, Any] = None,
        pathParams: Dict[str, Any] = None,
        body: Any = None,
        formParams: Dict[str, Any] = None,
        captures: List[ApiCapture] = None,
        lastResponseFile: str = None,
        lastStatusCode: int = None
    ):
        self.id = id
        self.baseUrl = baseUrl
        self.headers = headers or {}
        self.queryParams = queryParams or {}
        self.pathParams = pathParams or {}
        self.body = body
        self.formParams = formParams or {}
        self.captures = captures or []
        self.lastResponseFile = lastResponseFile
        self.lastStatusCode = lastStatusCode

    def to_dict(self):
        return {
            "id": self.id,
            "baseUrl": self.baseUrl,
            "headers": self.headers,
            "queryParams": self.queryParams,
            "pathParams": self.pathParams,
            "body": self.body,
            "formParams": self.formParams,
            "captures": [c.to_dict() for c in self.captures],
            "lastResponseFile": self.lastResponseFile,
            "lastStatusCode": self.lastStatusCode
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            id=data.get("id", "default"),
            baseUrl=data.get("baseUrl", ""),
            headers=data.get("headers", {}),
            queryParams=data.get("queryParams", {}),
            pathParams=data.get("pathParams", {}),
            body=data.get("body"),
            formParams=data.get("formParams", {}),
            captures=[ApiCapture.from_dict(c) for c in data.get("captures", [])],
            lastResponseFile=data.get("lastResponseFile"),
            lastStatusCode=data.get("lastStatusCode")
        )