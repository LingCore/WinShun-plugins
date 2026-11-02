"""index.json.sig 的签名与验签（用临时钥匙，不碰真钥匙）。"""
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import sign_index as si
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

SCRIPT = Path(si.__file__).resolve()
DATA = b'{"generated": "2026-11-02T00:00:00Z", "plugins": []}\n'


def new_key():
    return ec.generate_private_key(ec.SECP256R1())


def pem(key):
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption()).decode()


class Sign(unittest.TestCase):
    def test_sign_verify_and_tamper(self):
        key = new_key()
        xy = si.xy_of(key.public_key())
        rs = si.sign_bytes(key, DATA)
        self.assertEqual(len(rs), 64)
        self.assertTrue(si.verify_bytes(xy, DATA, rs))
        self.assertFalse(si.verify_bytes(xy, DATA[:-1] + b" ", rs))
        self.assertFalse(si.verify_bytes(si.xy_of(new_key().public_key()), DATA, rs))
        self.assertFalse(si.verify_bytes(xy, DATA, rs[:63]))

    def test_r_and_s_stay_32_bytes(self):
        key = new_key()
        for r, s in ((1, 2), (2**255, 1), (1, 2**255)):
            with patch.object(si, "decode_dss_signature", return_value=(r, s)):
                self.assertEqual(si.sign_bytes(key, DATA), r.to_bytes(32, "big") + s.to_bytes(32, "big"))
        for _ in range(40):  # 真签名里高位为 0 的情况也要是 64 字节
            self.assertEqual(len(si.sign_bytes(key, os.urandom(8))), 64)

    def run_cli(self, keys_dir, index, env_keys):
        env = {**os.environ, "INDEX_SIGNING_KEYS": env_keys}
        return subprocess.run([sys.executable, str(SCRIPT), "--keys-dir", str(keys_dir), "sign", str(index)],
                              env=env, capture_output=True, text=True, encoding="utf-8")

    def test_cli_sign_structure_and_verify(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "keys").mkdir()
            a, b = new_key(), new_key()
            (tmp / "keys" / "k-a.pub").write_text(si.xy_of(a.public_key()).hex() + "\n")
            (tmp / "keys" / "k-b.pub").write_text(si.xy_of(b.public_key()).hex() + "\n")
            index = tmp / "index.json"
            index.write_bytes(DATA)
            done = self.run_cli(tmp / "keys", index, pem(a) + pem(b))
            self.assertEqual(done.returncode, 0, done.stderr)
            raw = (tmp / "index.json.sig").read_bytes()
            self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
            self.assertNotIn(b"\r", raw)
            doc = json.loads(raw)
            self.assertEqual((doc["schema"], doc["file"]), (1, "index.json"))
            self.assertEqual([s["key"] for s in doc["signatures"]], ["k-a", "k-b"])
            for s in doc["signatures"]:
                self.assertEqual(s["algorithm"], "ecdsa-p256-sha256")
                self.assertEqual(len(base64.b64decode(s["signature"], validate=True)), 64)
            self.assertEqual(raw.decode(), si.registry.dumps(doc))
            verify = [sys.executable, str(SCRIPT), "--keys-dir", str(tmp / "keys"), "verify", str(index), str(index) + ".sig"]
            self.assertEqual(subprocess.run(verify, capture_output=True).returncode, 0)
            index.write_bytes(DATA + b" ")
            self.assertEqual(subprocess.run(verify, capture_output=True).returncode, 1)

    def test_unknown_private_key_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "keys").mkdir()
            (tmp / "keys" / "k-a.pub").write_text(si.xy_of(new_key().public_key()).hex() + "\n")
            index = tmp / "index.json"
            index.write_bytes(DATA)
            stranger = new_key()
            done = self.run_cli(tmp / "keys", index, pem(stranger))
            self.assertEqual(done.returncode, 1)
            self.assertFalse((tmp / "index.json.sig").exists())
            self.assertNotIn("PRIVATE", done.stdout + done.stderr)

    def test_verify_rejects_junk_and_wrong_algorithm(self):
        key = new_key()
        keys = {"k": si.xy_of(key.public_key())}
        good = base64.b64encode(si.sign_bytes(key, DATA)).decode()
        doc = lambda **kw: json.dumps({"schema": 1, "file": "index.json", "signatures": [
            {"key": "k", "algorithm": "ecdsa-p256-sha256", "signature": good, **kw}]})
        self.assertEqual(si.verify_document(DATA, doc(), keys), ["k"])
        self.assertEqual(si.verify_document(DATA, doc(algorithm="rsa"), keys), [])
        self.assertEqual(si.verify_document(DATA, doc(signature="!!!"), keys), [])
        self.assertEqual(si.verify_document(DATA, "not json", keys), [])


if __name__ == "__main__":
    unittest.main()
