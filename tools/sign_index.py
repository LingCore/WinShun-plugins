"""给 index.json 签名、验签（ECDSA P-256 + SHA-256，签名是 r||s 共 64 字节）。

  sign INDEX            私钥从环境变量 INDEX_SIGNING_KEYS 读（一个或多个首尾相接的 PEM），写 INDEX.sig，再自检
  verify INDEX SIG      用 keys/*.pub 验，至少一项通过返回 0，否则 1
  vector                用临时钥匙打印互通测试向量（公钥 hex、消息 Base64、签名 Base64）
  keygen ID --out DIR   生成私钥 DIR/ID.pem 和 keys/ID.pub；DIR 不能在仓库里

签的是 index.json 的原始字节。公钥文件 keys/<id>.pub：一行 128 个小写十六进制（X||Y），加 LF。
只依赖 cryptography，所以和只用标准库的 index.py 分开。私钥内容从不打印。
"""
from __future__ import annotations

import argparse
import base64
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # python -I 不会自己加脚本所在的文件夹
import registry  # noqa: E402

from cryptography.exceptions import InvalidSignature  # noqa: E402
from cryptography.hazmat.primitives import hashes, serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature, encode_dss_signature  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ALGORITHM = "ecdsa-p256-sha256"
KEY_ID_RE = re.compile(r"[a-z0-9-]{1,40}")
PUB_RE = re.compile(r"[0-9a-f]{128}")
PEM_RE = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S)


class SignError(Exception):
    pass


def xy_of(public_key: ec.EllipticCurvePublicKey) -> bytes:
    if not isinstance(public_key.curve, ec.SECP256R1):
        raise SignError("不是 P-256 钥匙")
    return public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)[1:]


def load_public_keys(keys_dir: Path) -> dict[str, bytes]:
    """keys/*.pub -> {id: X||Y}"""
    found: dict[str, bytes] = {}
    for path in sorted(keys_dir.glob("*.pub")):
        text = path.read_text(encoding="utf-8").strip()
        if not KEY_ID_RE.fullmatch(path.stem) or not PUB_RE.fullmatch(text):
            raise SignError(f"{path.name} 格式不对（要 128 个小写十六进制）")
        found[path.stem] = bytes.fromhex(text)
    return found


def sign_bytes(private_key: ec.EllipticCurvePrivateKey, data: bytes) -> bytes:
    der = private_key.sign(data, ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der)
    return r.to_bytes(32, "big") + s.to_bytes(32, "big")


def verify_bytes(xy: bytes, data: bytes, rs: bytes) -> bool:
    if len(xy) != 64 or len(rs) != 64:
        return False
    try:
        key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), b"\x04" + xy)
        key.verify(encode_dss_signature(int.from_bytes(rs[:32], "big"), int.from_bytes(rs[32:], "big")),
                   data, ec.ECDSA(hashes.SHA256()))
        return True
    except (InvalidSignature, ValueError):
        return False


def sig_document(entries: list[tuple[str, bytes]]) -> str:
    return registry.dumps({
        "schema": 1,
        "file": "index.json",
        "signatures": [{"key": k, "algorithm": ALGORITHM, "signature": base64.b64encode(rs).decode("ascii")}
                       for k, rs in entries],
    })


def verify_document(data: bytes, sig_text: str, keys: dict[str, bytes]) -> list[str]:
    """通过验证的 key id 列表。"""
    import json
    try:
        doc = json.loads(sig_text)
    except ValueError:
        return []
    if not isinstance(doc, dict) or doc.get("schema") != 1 or not isinstance(doc.get("signatures"), list):
        return []
    ok = []
    for item in doc["signatures"][:4]:
        if not isinstance(item, dict) or item.get("algorithm") != ALGORITHM:
            continue
        key_id, text = item.get("key"), item.get("signature")
        if not isinstance(key_id, str) or key_id not in keys or not isinstance(text, str):
            continue
        try:
            rs = base64.b64decode(text, validate=True)
        except ValueError:
            continue
        if verify_bytes(keys[key_id], data, rs):
            ok.append(key_id)
    return ok


def load_private_keys(text: str) -> list[ec.EllipticCurvePrivateKey]:
    blocks = PEM_RE.findall(text)
    if not blocks:
        raise SignError("INDEX_SIGNING_KEYS 里没有私钥")
    keys = []
    for block in blocks:
        try:
            key = serialization.load_pem_private_key(block.encode("ascii"), password=None)
        except (ValueError, TypeError, UnicodeError):
            raise SignError("INDEX_SIGNING_KEYS 里有读不出的私钥") from None
        if not isinstance(key, ec.EllipticCurvePrivateKey) or not isinstance(key.curve, ec.SECP256R1):
            raise SignError("INDEX_SIGNING_KEYS 里有不是 P-256 的私钥")
        keys.append(key)
    return keys


def cmd_sign(args) -> int:
    index = Path(args.index)
    data = index.read_bytes()
    pubs = load_public_keys(Path(args.keys_dir))
    if not pubs:
        raise SignError(f"{args.keys_dir} 里没有 .pub 公钥")
    by_xy = {xy: key_id for key_id, xy in pubs.items()}
    entries: list[tuple[str, bytes]] = []
    for private in load_private_keys(os.environ.get("INDEX_SIGNING_KEYS", "")):
        key_id = by_xy.get(xy_of(private.public_key()))
        if key_id is None:
            raise SignError("有一把私钥在 keys/ 里找不到对应的公钥，拒绝签名")
        if any(k == key_id for k, _ in entries):
            raise SignError(f"{key_id} 重复了")
        entries.append((key_id, sign_bytes(private, data)))
    sig_path = Path(str(index) + ".sig")
    sig_path.write_bytes(sig_document(entries).encode("utf-8"))
    # 自检：重新读两个文件，每一项都要能用 keys/*.pub 验过
    good = verify_document(index.read_bytes(), sig_path.read_text(encoding="utf-8"), pubs)
    if sorted(good) != sorted(k for k, _ in entries):
        sig_path.unlink(missing_ok=True)
        raise SignError("自检没过，没有写出签名")
    print(f"signed {index.name} with {', '.join(k for k, _ in entries)}")
    return 0


def cmd_verify(args) -> int:
    pubs = load_public_keys(Path(args.keys_dir))
    try:
        data = Path(args.index).read_bytes()
        sig_text = Path(args.sig).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as e:
        print(f"读不了文件：{e.__class__.__name__}", file=sys.stderr)
        return 1
    good = verify_document(data, sig_text, pubs)
    if not good:
        print("签名无效或缺失", file=sys.stderr)
        return 1
    print(f"signature ok ({', '.join(good)})")
    return 0


def cmd_vector(args) -> int:
    private = ec.generate_private_key(ec.SECP256R1())
    message = os.urandom(24) + b" WinShun index vector\n"
    print("public  :", xy_of(private.public_key()).hex())
    print("message :", base64.b64encode(message).decode("ascii"))
    print("signature:", base64.b64encode(sign_bytes(private, message)).decode("ascii"))
    return 0


def cmd_keygen(args) -> int:
    if not KEY_ID_RE.fullmatch(args.id):
        raise SignError("id 只能是小写字母、数字、连字符，最多 40 个")
    out = Path(args.out).resolve()
    if out == ROOT or ROOT in out.parents:
        raise SignError("私钥不能写在仓库里，--out 换一个仓库外的文件夹")
    out.mkdir(parents=True, exist_ok=True)
    pem_path = out / f"{args.id}.pem"
    pub_path = Path(args.keys_dir) / f"{args.id}.pub"
    if pem_path.exists() or pub_path.exists():
        raise SignError("同名的钥匙已经有了，不覆盖")
    private = ec.generate_private_key(ec.SECP256R1())
    pem_path.write_bytes(private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                               serialization.NoEncryption()))
    pub_path.parent.mkdir(parents=True, exist_ok=True)
    pub_path.write_bytes((xy_of(private.public_key()).hex() + "\n").encode("ascii"))
    print(f"私钥写到 {pem_path}（别提交、别发给别人）；公钥写到 {pub_path}")
    print(f'app 里用：{{u"{args.id}", "{xy_of(private.public_key()).hex()}"}},')
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--keys-dir", default=str(ROOT / "keys"), help="公钥文件夹，默认仓库的 keys/（测试用）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("sign")
    p.add_argument("index")
    p.set_defaults(fn=cmd_sign)
    p = sub.add_parser("verify")
    p.add_argument("index")
    p.add_argument("sig")
    p.set_defaults(fn=cmd_verify)
    p = sub.add_parser("vector")
    p.set_defaults(fn=cmd_vector)
    p = sub.add_parser("keygen")
    p.add_argument("id")
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_keygen)
    args = ap.parse_args()
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    try:
        return args.fn(args)
    except SignError as e:
        print(f"错误：{e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
