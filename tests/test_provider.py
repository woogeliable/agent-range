import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from arange.runtime.provider import ModelProvider, ModelUnavailable


def env(**overrides):
    base = {
        "AR_MODEL_ENABLED": "1",
        "AR_MODEL_URL": "https://models.example.com/v1/chat/completions",
        "AR_MODEL_NAME": "demo-model",
        "AR_MODEL_KEY": "test-key",
        "AR_MODEL_ALLOWED_HOSTS": "models.example.com",
    }
    base.update(overrides)
    return base


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit=None):
        return self.payload


class FakeOpener:
    def __init__(self, payload):
        self.payload = payload
        self.requests = []

    def open(self, request, timeout=20):
        self.requests.append(request)
        return FakeResponse(self.payload)


class ProviderTests(unittest.TestCase):
    def test_disabled_by_default(self):
        provider = ModelProvider({})
        self.assertFalse(provider.status()["enabled"])
        with self.assertRaises(ModelUnavailable):
            provider.validate()

    def test_valid_https_configuration(self):
        provider = ModelProvider(env())
        self.assertTrue(provider.status()["enabled"])
        provider.validate()

    def test_http_is_rejected(self):
        with self.assertRaises(ModelUnavailable):
            ModelProvider(env(AR_MODEL_URL="http://models.example.com/v1/chat")).validate()

    def test_ip_literal_is_rejected(self):
        with self.assertRaises(ModelUnavailable):
            ModelProvider(
                env(
                    AR_MODEL_URL="https://10.0.0.5/v1/chat",
                    AR_MODEL_ALLOWED_HOSTS="10.0.0.5",
                )
            ).validate()

    def test_host_and_port_are_enforced(self):
        with self.assertRaises(ModelUnavailable):
            ModelProvider(env(AR_MODEL_ALLOWED_HOSTS="other.example.com")).validate()
        with self.assertRaises(ModelUnavailable):
            ModelProvider(env(AR_MODEL_URL="https://models.example.com:8443/v1/chat")).validate()
        with self.assertRaises(ModelUnavailable):
            ModelProvider(env(AR_MODEL_URL="https://models.example.com/v1/chat?x=1")).validate()

    def test_complete_parses_openai_shape(self):
        opener = FakeOpener(
            json.dumps({"choices": [{"message": {"content": "模拟回答"}}]}).encode("utf-8")
        )
        provider = ModelProvider(env(), opener=opener)
        result = provider.complete("系统提示", "用户消息")
        self.assertEqual(result["answer"], "模拟回答")
        self.assertEqual(provider.calls, 1)
        self.assertEqual(len(opener.requests), 1)
        self.assertEqual(opener.requests[0].get_header("Authorization"), "Bearer test-key")

    def test_input_limits_and_budget(self):
        provider = ModelProvider(env(), opener=FakeOpener(b"{}"))
        with self.assertRaises(ValueError):
            provider.complete("x" * 5000, "hi")
        provider.calls = provider.limit
        with self.assertRaises(ModelUnavailable):
            provider.complete("system", "user")


if __name__ == "__main__":
    unittest.main()
