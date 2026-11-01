#!/usr/bin/env python3
"""AgentRange 3.3 — local-first AI application security range."""
import argparse
import os
import sys

from arange import __version__, config
from arange.app import App, make_server

LOOPBACK = {"127.0.0.1", "::1", "localhost"}


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="agent-range",
        description="AgentRange 3.3 — AI application security range (local-first).",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("HOST", config.DEFAULT_HOST),
        help="bind address (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("PORT", str(config.DEFAULT_PORT))),
        help="bind port (default: 8787)",
    )
    args = parser.parse_args(argv)

    app = App()
    try:
        httpd = make_server(args.host, args.port, app)
    except OSError as exc:
        print("无法启动：%s" % exc, file=sys.stderr)
        print("端口被占用？试试 --port 8788", file=sys.stderr)
        return 1

    bound_host, bound_port = httpd.server_address[:2]
    print("")
    print("  AgentRange %s · AI 应用安全靶场" % __version__)
    print("  ────────────────────────────────────")
    print("  关卡     %d 个（课程地图在首页）" % len(app.lessons))
    print("  地址     http://%s:%s" % (bound_host, bound_port))
    print("  数据     %s" % config.DATA_DIR)
    print("  模型     确定性模拟目标（默认离线，零外网）")
    print("")
    if config.ALLOW_EMBED:
        print("  ⚠ 已允许被嵌入（AR_RANGE_ALLOW_EMBED=1），仅用于预览代理。", flush=True)
    if args.host not in LOOPBACK:
        print("  ⚠ 正在监听非 loopback 地址。这是教学靶场，请勿直接暴露公网。", flush=True)
    else:
        print("  按 Ctrl+C 停止。", flush=True)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。", flush=True)
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
