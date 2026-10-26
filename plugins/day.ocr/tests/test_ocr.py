import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import urllib.error

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from PIL import Image
from ocr_api import OcrError, endpoint_url, image_png, recognize
from protocol import serve


class ApiTests(unittest.TestCase):
    def test_exact_multimodal_request_and_text(self):
        def opener(request, timeout):
            self.assertEqual(request.full_url, "https://vision.example/v1/chat/completions")
            self.assertEqual(timeout, 90)
            payload = json.loads(request.data)
            self.assertEqual(payload["model"], "my-vision-model")
            self.assertNotIn("thinking", payload)
            self.assertNotIn("max_tokens", payload)
            image = payload["messages"][0]["content"][1]
            self.assertEqual(image["image_url"]["url"], "data:image/png;base64,cG5n")
            self.assertEqual(image["image_url"]["detail"], "high")
            return io.BytesIO(json.dumps({"choices": [{"message": {"content": " 你好\nOCR "}, "finish_reason": "stop"}]}).encode())
        self.assertEqual(recognize(b"png", {"apiKey": "test-key", "endpoint": "https://vision.example/v1", "model": "my-vision-model"}, opener), "你好\nOCR")

    def test_no_key_no_network(self):
        with patch("urllib.request.build_opener") as opener:
            with self.assertRaises(OcrError):
                recognize(b"png", {})
            opener.assert_not_called()

    def test_endpoint_validation(self):
        self.assertEqual(endpoint_url("https://example.com/v1/"), "https://example.com/v1/chat/completions")
        self.assertEqual(endpoint_url("https://example.com/chat/completions"), "https://example.com/chat/completions")
        self.assertEqual(endpoint_url("http://localhost:1234/v1"), "http://localhost:1234/v1/chat/completions")
        for value in ("http://example.com", "https://user:secret@example.com", "https://example.com?key=secret"):
            with self.subTest(value=value), self.assertRaises(OcrError):
                endpoint_url(value)

    def test_status_does_not_leak_response_or_key(self):
        def opener(request, timeout):
            raise urllib.error.HTTPError(request.full_url, 401, "secret-response", {}, io.BytesIO(b"secret-key"))
        with self.assertRaises(OcrError) as result:
            recognize(b"png", {"apiKey": "secret-key", "endpoint": "https://vision.example", "model": "vision"}, opener)
        self.assertIn("401", str(result.exception))
        self.assertNotIn("secret", str(result.exception))

    def test_truncation_and_malformed_response(self):
        for payload in ({}, {"choices": [{"message": {"content": "text"}, "finish_reason": "length"}]}, {"choices": [{"message": {"content": ""}}]}):
            with self.subTest(payload=payload), self.assertRaises(OcrError):
                recognize(b"png", {"apiKey": "test", "endpoint": "https://vision.example", "model": "vision"}, lambda *a, **k: io.BytesIO(json.dumps(payload).encode()))

    def test_png_and_dimension_limit(self):
        self.assertTrue(image_png(Image.new("RGB", (20, 30))).startswith(b"\x89PNG"))
        with self.assertRaises(OcrError):
            image_png(Image.new("RGB", (8193, 1)))


class ProtocolTests(unittest.TestCase):
    def test_lifecycle_without_network_or_ui_calls(self):
        messages = [
            {"id": 1, "method": "initialize", "params": {"settings": {"apiKey": "secret"}}},
            {"id": 2, "method": "query", "params": {"text": ""}},
            {"id": 3, "method": "action"},
            {"method": "settingsChanged", "params": {"settings": {"model": "other"}}},
            {"id": 4, "method": "shutdown"}]
        events, output = [], io.StringIO()
        serve(io.StringIO("\n".join(json.dumps(m) for m in messages)), output, events.append)
        replies = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual([m["id"] for m in replies], [1, 2, 3, 4])
        self.assertEqual(replies[0]["result"]["protocolVersion"], "1")
        self.assertEqual([e[0] for e in events], ["settings", "show", "show", "settings", "quit"])
        self.assertNotIn("secret", output.getvalue())

    def test_eof_and_malformed_input(self):
        events, output = [], io.StringIO()
        serve(io.StringIO('not-json\n[]\n{"id":1,"method":"query","params":[]}\n'), output, events.append)
        self.assertEqual(events[-1][0], "quit")


if __name__ == "__main__":
    unittest.main()
