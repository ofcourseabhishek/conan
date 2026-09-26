"""Closed set of user-facing error codes (TRD §7), each with a message and a next step."""

from fastapi import Request
from fastapi.responses import JSONResponse

from app.schemas import ApiError, ErrorCode

CATALOG: dict[str, tuple[int, str, str]] = {
    "NOT_PDF": (415, "That file isn't a PDF.", "Upload a text-based PDF, or try the sample contract."),
    "TOO_LARGE": (413, "That PDF is over 10 MB.", "Upload a smaller PDF, or try the sample contract."),
    "TOO_MANY_PAGES": (413, "That PDF has more than 30 pages.", "Upload a shorter contract, or try the sample contract."),
    "ENCRYPTED": (422, "That PDF is password-protected.", "Remove the password and upload again, or try the sample contract."),
    "NO_TEXT_LAYER": (422, "This looks like a scanned PDF. Conan needs a text-based PDF.", "Try the sample contract."),
    "LLM_QUOTA": (503, "The AI quota for today is used up.", "View the sample analysis instead."),
    "LLM_UNAVAILABLE": (503, "The AI service isn't responding right now.", "Try again in a minute, or view the sample analysis."),
    "PARTIAL_EXTRACTION": (200, "Some clauses could not be analyzed.", "Review the flagged clauses manually."),
    "EMPTY_EXTRACTION": (422, "No obligations were found in this contract.", "Check that it is a contract, or try the sample contract."),
    "INTERNAL": (500, "Something went wrong on our side.", "Try again, or view the sample analysis."),
}


class ConanError(Exception):
    def __init__(self, code: ErrorCode, detail: str | None = None):
        super().__init__(detail or code)
        self.code = code

    @property
    def status(self) -> int:
        return CATALOG[self.code][0]

    def to_api(self) -> ApiError:
        _, message, action = CATALOG[self.code]
        return ApiError(error_code=self.code, message=message, action=action)


async def conan_error_handler(_: Request, exc: ConanError) -> JSONResponse:
    return JSONResponse(status_code=exc.status, content=exc.to_api().model_dump())
