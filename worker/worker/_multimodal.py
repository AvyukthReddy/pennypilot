import base64


def text_part(text: str) -> dict:
    return {"type": "text", "text": text}


def image_part(image_bytes: bytes, mime: str = "image/png") -> dict:
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}}
