"""Deterministic instruction-resolution model.

This is deliberately *not* a real language model. It is a small, inspectable
decision engine: it extracts directives from every context segment, resolves
them according to the active defence profile, and only then acts. Attacks work
by getting a directive from an untrusted segment accepted -- not by matching a
hard-coded sentence from the tutorial.
"""
import re

from ..world import find_owner

LEVELS = ("vulnerable", "basic", "hardened", "reference")

LEVEL_LABELS = {
    "vulnerable": "漏洞版",
    "basic": "基础过滤",
    "hardened": "加固版",
    "reference": "参考实现",
}

LEVEL_NOTES = {
    "vulnerable": "没有任何信任边界：谁最后说话就听谁的。",
    "basic": "加了关键词黑名单。能挡住教程原句，挡不住改写。",
    "hardened": "信任标签 + 指令/数据分离 + 检索 ACL + 出口白名单。",
    "reference": "在加固版之上加入审批、能力范围与输出 DLP。",
}

PROFILES = {
    "vulnerable": {
        "untrusted_directives": True,
        "reveal_system": True,
        "egress": "any",
        "acl": "off",
        "blocklist": False,
        "output_dlp": False,
        "approval": False,
    },
    "basic": {
        "untrusted_directives": True,
        "reveal_system": True,
        "egress": "any",
        "acl": "off",
        "blocklist": True,
        "output_dlp": False,
        "approval": False,
    },
    "hardened": {
        "untrusted_directives": False,
        "reveal_system": False,
        "egress": "allowlist",
        "acl": "on",
        "blocklist": False,
        "output_dlp": True,
        "approval": False,
    },
    "reference": {
        "untrusted_directives": False,
        "reveal_system": False,
        "egress": "allowlist",
        "acl": "on",
        "blocklist": False,
        "output_dlp": True,
        "approval": True,
    },
}

ALLOWED_DOMAINS = {"bluebird.internal"}

BLOCKLIST = (
    "忽略",
    "无视",
    "ignore",
    "系统提示词",
    "system prompt",
    "开发者模式",
    "developer mode",
)

OVERRIDE = re.compile(
    r"(忽略|无视|不要遵守|不再遵守|绕过|忘掉|忘记|从现在开始|新的?指令|系统指令|管理员指令|"
    r"开发者模式|调试模式|最高优先级|override|ignore|disregard|forget|new instructions?|"
    r"developer mode|jailbreak|system\s*:)",
    re.I,
)
SECRET = re.compile(
    r"(口令|密钥|优惠码|内部代码|内部规则|系统提示词?|提示词|规则原文|配置|"
    r"secret|token|coupon|system prompt|instructions?|规则|prompt)",
    re.I,
)
REVEAL = re.compile(
    r"(告诉|输出|重复|复述|打印|展示|泄露|给出|说出|原文|逐字|"
    r"reveal|print|repeat|show|tell|dump|leak|display)",
    re.I,
)
SEND = re.compile(r"(发送|发给|寄给|邮件|邮箱|send|mail|email|转发|forward)", re.I)
EMAIL = re.compile(r"([A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})")
CANCEL = re.compile(r"(取消|cancel)", re.I)
ORDER = re.compile(r"(订单|order)", re.I)
WARRANTY = re.compile(r"(保修|质保|warranty)", re.I)
NUM_DAYS = re.compile(r"(\d{1,4})\s*(天|日|days?)", re.I)
ANSWER_VERB = re.compile(
    r"(回答|改为|改成|设置为|设为|调整为|说|标注|写成|answer|set|change|say|respond)",
    re.I,
)
FETCH = re.compile(r"(访问|请求|打开|抓取|fetch|curl|visit|get)", re.I)
URL = re.compile(r"(https?://[^\s，。；;'\"<>]+)", re.I)


def profile_for(level):
    return PROFILES.get(level, PROFILES["vulnerable"])


def is_blocked(text):
    lowered = (text or "").lower()
    for word in BLOCKLIST:
        if word.lower() in lowered:
            return word
    return None


def egress_allowed(recipient, profile):
    if profile.get("egress") == "any":
        return True
    if not recipient or "@" not in recipient:
        return False
    domain = recipient.rsplit("@", 1)[-1].strip().lower()
    return domain in ALLOWED_DOMAINS


def extract_directives(text):
    """Turn a piece of text into candidate actions.

    The same extractor runs over the user turn and over retrieved documents,
    which is exactly why an injected document can change the agent's actions.
    """
    text = text or ""
    directives = []
    override = bool(OVERRIDE.search(text))

    if (REVEAL.search(text) and SECRET.search(text)) or (override and SECRET.search(text)):
        directives.append({"kind": "leak_secret", "override": override})

    for email in EMAIL.findall(text):
        if SEND.search(text) or override:
            directives.append({"kind": "send_mail", "to": email.lower()})

    if CANCEL.search(text) and ORDER.search(text):
        directives.append({"kind": "cancel_order", "owner": find_owner(text)})

    if WARRANTY.search(text):
        match = NUM_DAYS.search(text)
        if match and (ANSWER_VERB.search(text) or override):
            directives.append(
                {"kind": "set_fact", "fact": "warranty_days", "value": int(match.group(1))}
            )

    for url in URL.findall(text):
        if FETCH.search(text) or override:
            directives.append({"kind": "fetch_url", "url": url})

    deduped = []
    seen = set()
    for directive in directives:
        key = (directive["kind"], tuple(sorted((k, str(v)) for k, v in directive.items())))
        if key not in seen:
            seen.add(key)
            deduped.append(directive)
    return deduped
