"""The synthetic world every lesson runs against.

Everything here is fictional: tenants, documents, orders, mail and the fake
network. Nothing touches the real filesystem, network or a subprocess.
"""
import copy
import hashlib
import hmac
import re


def make_canary(secret, user_id, lesson_id, attempt_id, prefix="AR"):
    message = ("%s|%s|%s" % (user_id, lesson_id, attempt_id)).encode("utf-8")
    digest = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()[:10].upper()
    return "%s-%s" % (prefix, digest)


def _fill(value, canary):
    if isinstance(value, str):
        return value.replace("{{canary}}", canary)
    if isinstance(value, list):
        return [_fill(item, canary) for item in value]
    if isinstance(value, dict):
        return {key: _fill(item, canary) for key, item in value.items()}
    return value


def build(lesson, user_id, attempt_id, secret, doc_text=None):
    target = lesson.get("target") or {}
    canary = make_canary(
        secret,
        user_id,
        lesson["id"],
        attempt_id,
        target.get("canary_prefix", "AR"),
    )
    docs = copy.deepcopy(target.get("docs") or [])
    for doc in docs:
        doc.setdefault("trust", "trusted")
        doc.setdefault("acl", ["A", "B"])
        doc.setdefault("keywords", [])
    editable = target.get("editable_doc")
    if editable and doc_text:
        for doc in docs:
            if doc.get("id") == editable:
                doc["text"] = doc_text
                break
    world = {
        "canary": canary,
        "tenant": target.get("tenant", "A"),
        "user": target.get("user", "alice"),
        "facts": copy.deepcopy(target.get("facts") or {}),
        "system_prompt": _fill(target.get("system_prompt", ""), canary),
        "policy": target.get("policy", ""),
        "docs": _fill(docs, canary),
        "orders": copy.deepcopy(target.get("orders") or {}),
        "mail": [],
        "http": [],
        "tickets": [],
        "memory": [],
        "tools": list(target.get("tools") or []),
        "flags": {},
        "meta": {
            "lesson_id": lesson["id"],
            "editable_doc": editable,
            "doc_text": doc_text,
            "canary_prefix": target.get("canary_prefix", "AR"),
        },
    }
    return world


def editable_text(world):
    doc_id = world.get("meta", {}).get("editable_doc")
    for doc in world.get("docs", []):
        if doc.get("id") == doc_id:
            return doc.get("text", "")
    return ""


def select_documents(world, query, acl_on):
    """Keyword-driven retrieval. Deterministic, inspectable, and small."""
    selected = []
    query_lower = (query or "").lower()
    for doc in world.get("docs", []):
        score = 0
        for keyword in doc.get("keywords") or []:
            if keyword.lower() in query_lower:
                score += 2
        if doc.get("always"):
            score += 1
        if score <= 0:
            continue
        allowed = (not acl_on) or world.get("tenant") in (doc.get("acl") or [])
        selected.append(
            {
                "id": doc.get("id"),
                "title": doc.get("title", doc.get("id")),
                "trust": doc.get("trust", "trusted"),
                "acl": doc.get("acl") or [],
                "allowed": allowed,
                "score": score,
                "text": doc.get("text", ""),
            }
        )
    selected.sort(key=lambda item: (-item["score"], item["id"] or ""))
    return selected[:3]


def set_fact(world, name, value):
    world.setdefault("facts", {})[name] = value


def get_fact(world, name):
    return (world.get("facts") or {}).get(name)


def find_owner(text):
    match = re.search(r"(?:^|[^A-Za-z0-9])([AB])(?:[^A-Za-z0-9]|$)", text or "")
    return match.group(1).upper() if match else None
