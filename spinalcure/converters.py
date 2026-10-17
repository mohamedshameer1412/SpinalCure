from .utils import encode_b64uuid, decode_b64uuid

class B64UUIDConverter:
    """
    Custom URL converter for URL-safe base64 encoded UUIDs.
    Matches 22 url-safe base64 characters.
    """
    regex = r'[A-Za-z0-9_-]{22}'

    def to_python(self, value):
        # Decode base64 to UUID for the view
        decoded_uuid = decode_b64uuid(value)
        if decoded_uuid is None:
            raise ValueError
        return decoded_uuid

    def to_url(self, value):
        # Encode UUID to base64 for the URL
        encoded = encode_b64uuid(value)
        if encoded is None:
            raise ValueError
        return encoded
