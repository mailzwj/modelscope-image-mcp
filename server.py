#!/usr/bin/env python3
"""
MCP Server for ModelScope Image Generation.

This server provides tools to generate images using ModelScope's image generation API.
"""

import json
import time
import base64
from typing import Optional, Dict, Any

import httpx
from pydantic import BaseModel, Field, field_validator, ConfigDict
from mcp.server.fastmcp import FastMCP

# Initialize the MCP server
mcp = FastMCP("modelscope_image_mcp")

# Constants
API_BASE_URL = "https://api-inference.modelscope.cn"
DEFAULT_MODEL = "Qwen/Qwen-Image-2512"
POLL_INTERVAL = 5  # seconds
TIMEOUT = 300  # 5 minutes max wait for image generation


class ImageGenerationInput(BaseModel):
    """Input model for image generation tool."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True
    )

    token: str = Field(
        ...,
        description="ModelScope API authentication token (Bearer token)",
        min_length=10
    )
    prompt: str = Field(
        ...,
        description="Image content description/prompt in English",
        min_length=1,
        max_length=2000
    )
    size: str = Field(
        default="1024x1024",
        description="Image size in format 'WIDTHxHEIGHT' (e.g., '1024x1024', '1536x864'). Both dimensions must be <= 2048"
    )
    model: str = Field(
        default=DEFAULT_MODEL,
        description="Model to use for image generation"
    )

    @field_validator('size')
    @classmethod
    def validate_size_format(cls, v: str) -> str:
        """Validate size format is 'WIDTHxHEIGHT' with both dimensions <= 2048."""
        if not isinstance(v, str):
            raise ValueError("Size must be a string in format 'WIDTHxHEIGHT'")
        
        v = v.strip()
        if 'x' not in v:
            raise ValueError("Size must be in format 'WIDTHxHEIGHT' (e.g., '1024x1024')")
        
        try:
            width, height = map(int, v.split('x'))
        except ValueError:
            raise ValueError("Width and height must be integers (e.g., '1024x1024')")
        
        if width < 1 or height < 1:
            raise ValueError("Width and height must be positive integers")
        if width > 2048 or height > 2048:
            raise ValueError("Width and height must be <= 2048")
        
        return f"{width}x{height}"


class ImageGenerationOutput(BaseModel):
    """Output model for successful image generation."""
    success: bool
    image_url: str
    task_id: str
    size: str
    prompt: str


def _handle_api_error(e: Exception) -> str:
    """Format API errors consistently."""
    if isinstance(e, httpx.HTTPStatusError):
        if e.response.status_code == 401:
            return "Error: Invalid or expired API token. Please check your ModelScope token."
        elif e.response.status_code == 403:
            return "Error: Permission denied. Your token doesn't have access to this resource."
        elif e.response.status_code == 429:
            return "Error: Rate limit exceeded. Please wait before making more requests."
        elif e.response.status_code == 400:
            try:
                error_detail = e.response.json().get("message", str(e))
                return f"Error: Bad request - {error_detail}"
            except Exception:
                return f"Error: Bad request - {str(e)}"
        return f"Error: API request failed with status {e.response.status_code}: {str(e)}"
    elif isinstance(e, httpx.TimeoutException):
        return "Error: Request timed out. Please try again."
    else:
        return f"Error: Unexpected error occurred: {type(e).__name__}: {str(e)}"


async def _generate_image_async(
    token: str,
    prompt: str,
    size: str,
    model: str
) -> Dict[str, Any]:
    """Generate image using ModelScope async API with polling."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-ModelScope-Async-Mode": "true"
    }

    # Parse size to get dimensions
    # width, height = map(int, size.split("x"))

    # Submit generation request
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{API_BASE_URL}/v1/images/generations",
            headers=headers,
            json={
                "model": model,
                "prompt": prompt,
                "size": size,
            }
        )
        response.raise_for_status()
        task_data = response.json()
        task_id = task_data.get("task_id")

        if not task_id:
            return {"success": False, "error": "No task_id returned from API"}

    # Poll for task completion
    start_time = time.time()
    poll_headers = {
        "Authorization": f"Bearer {token}",
        "X-ModelScope-Task-Type": "image_generation"
    }

    while time.time() - start_time < TIMEOUT:
        async with httpx.AsyncClient(timeout=30.0) as client:
            result = await client.get(
                f"{API_BASE_URL}/v1/tasks/{task_id}",
                headers=poll_headers
            )
            result.raise_for_status()
            data = result.json()

            task_status = data.get("task_status")

            if task_status == "SUCCEED":
                output_images = data.get("output_images", [])
                if output_images:
                    return {
                        "success": True,
                        "image_url": output_images[0],
                        "task_id": task_id,
                        "size": size,
                        "prompt": prompt
                    }
                return {"success": False, "error": "No images in response"}

            elif task_status == "FAILED":
                error_msg = data.get("message", "Image generation failed")
                return {"success": False, "error": error_msg}

        time.sleep(POLL_INTERVAL)

    return {"success": False, "error": "Image generation timed out"}


def _format_success_response(data: Dict[str, Any]) -> str:
    """Format successful image generation as JSON."""
    result = {
        "success": True,
        "task_id": data["task_id"],
        "image_url": data["image_url"],
        "size": data["size"],
        "prompt": data["prompt"]
    }
    return json.dumps(result, indent=2, ensure_ascii=False)


def _format_error_response(error: str) -> str:
    """Format error as JSON."""
    result = {
        "success": False,
        "error": error
    }
    return json.dumps(result, indent=2, ensure_ascii=False)


def _format_error_response(error: str) -> str:
    """Format error as markdown."""
    return f"# Error\n\n{error}"


@mcp.tool(
    name="modelscope_generate_image",
    annotations={
        "title": "Generate Image with ModelScope",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True
    }
)
async def modelscope_generate_image(params: ImageGenerationInput) -> str:
    """
    Generate an image using ModelScope's AI image generation service.

    This tool calls the ModelScope (魔搭) platform API to generate images from text prompts.
    It uses asynchronous task processing - the API is called to start generation,
    then polls for completion.

    Args:
        params (ImageGenerationInput): Validated input parameters containing:
            - token (str): ModelScope API authentication token (Bearer token)
            - prompt (str): Image content description in English
            - size (str): Image dimensions in format 'WIDTHxHEIGHT' (default: '1024x1024')
            - model (str): Model to use (default: Qwen/Qwen-Image-2512)

    #JH|    Returns:
        #HM|        str: JSON-formatted response containing:
            #VY|            - Success: {success: true, task_id, image_url, size, prompt}
            #WQ|            - Error: {success: false, error: "message"}

    Examples:
        - Use when: "Generate a cat image" -> params with prompt="A cute orange cat sitting on a sofa"
        - Use when: "Create a landscape" -> params with prompt="Sunset over mountains with pink clouds"
        - Don't use when: You need synchronous generation (this is async with polling)

    Error Handling:
        - Returns "Error: Invalid or expired API token" if token is invalid (401)
        - Returns "Error: Permission denied" if no access (403)
        - Returns "Error: Rate limit exceeded" if too many requests (429)
        - Returns "Error: Bad request" if prompt is invalid (400)
        - Returns timeout error if generation takes more than 5 minutes
    """
    try:
        result = await _generate_image_async(
            token=params.token,
            prompt=params.prompt,
            size=params.size,  # size is now a string, not enum
            model=params.model
        )

        if result.get("success"):
            return _format_success_response(result)
        else:
            return _format_error_response(result.get("error", "Unknown error"))

    except Exception as e:
        return _format_error_response(_handle_api_error(e))


if __name__ == "__main__":
    mcp.run()
