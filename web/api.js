const CSRF = { "X-AR-CSRF": "1" };

export async function api(path, options = {}) {
  const init = {
    method: options.method || "GET",
    credentials: "same-origin",
    headers: Object.assign({}, CSRF),
  };
  if (options.body !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(options.body);
  }
  let response;
  try {
    response = await fetch(path, init);
  } catch (error) {
    throw new Error("无法连接服务器，请确认靶场仍在运行。");
  }
  let data = {};
  try {
    data = await response.json();
  } catch (error) {
    data = {};
  }
  if (!response.ok) {
    throw new Error(data.message || data.error || `HTTP ${response.status}`);
  }
  return data;
}

export function esc(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

let toastTimer = null;
export function toast(message, kind = "info") {
  const node = document.getElementById("toast");
  if (!node) return;
  node.textContent = message;
  node.className = `toast show ${kind}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    node.className = "toast";
  }, 4200);
}

export const LEVEL_META = {
  vulnerable: { label: "漏洞版", short: "L0", note: "没有信任边界：谁最后说话就听谁的。" },
  basic: { label: "基础过滤", short: "L1", note: "关键词黑名单：挡得住教程原句，挡不住改写。" },
  hardened: { label: "加固版", short: "L2", note: "信任标签 + 检索 ACL + 出口白名单。" },
  reference: { label: "参考实现", short: "L3", note: "在加固版上加入审批、能力范围与输出 DLP。" },
};

export function levelLabel(level) {
  return (LEVEL_META[level] && LEVEL_META[level].label) || level;
}

export function levelNote(level) {
  return (LEVEL_META[level] && LEVEL_META[level].note) || "";
}

export function difficultyDots(value) {
  const n = Math.max(0, Math.min(3, Number(value) || 0));
  let html = '<span class="dots" aria-label="难度 ' + n + '">';
  for (let i = 0; i < 3; i += 1) {
    html += `<span class="dot ${i < n ? "on" : ""} ${i < n && n >= 3 ? "hot" : ""}"></span>`;
  }
  return html + "</span>";
}

export function shortTime(ts) {
  if (!ts) return "";
  try {
    return new Date(ts * 1000).toLocaleTimeString("zh-CN", {
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch (error) {
    return "";
  }
}

export function diffLines(before, after) {
  const a = String(before || "").split("\n");
  const b = String(after || "").split("\n");
  const grid = Array.from({ length: a.length + 1 }, () => new Array(b.length + 1).fill(0));
  for (let i = a.length - 1; i >= 0; i -= 1) {
    for (let j = b.length - 1; j >= 0; j -= 1) {
      grid[i][j] = a[i] === b[j] ? grid[i + 1][j + 1] + 1 : Math.max(grid[i + 1][j], grid[i][j + 1]);
    }
  }
  const out = [];
  let i = 0;
  let j = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {
      out.push({ type: "same", text: a[i] });
      i += 1;
      j += 1;
    } else if (grid[i + 1][j] >= grid[i][j + 1]) {
      out.push({ type: "del", text: a[i] });
      i += 1;
    } else {
      out.push({ type: "add", text: b[j] });
      j += 1;
    }
  }
  while (i < a.length) {
    out.push({ type: "del", text: a[i] });
    i += 1;
  }
  while (j < b.length) {
    out.push({ type: "add", text: b[j] });
    j += 1;
  }
  return out;
}

const ICONS = {
  arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>',
  play: '<path d="M8 5v14l11-7z"/>',
  shield: '<path d="M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6z"/><path d="M9 12l2 2 4-4"/>',
  terminal: '<path d="M4 5h16v14H4z"/><path d="M8 9l3 3-3 3M13 15h4"/>',
  check: '<path d="M4 12l5 5L20 6"/>',
  refresh: '<path d="M3 12a9 9 0 0115-6.7L21 8M21 3v5h-5"/><path d="M21 12a9 9 0 01-15 6.7L3 16M3 21v-5h5"/>',
  bulb: '<path d="M9 18h6M10 22h4"/><path d="M12 2a7 7 0 00-4 12.7V17h8v-2.3A7 7 0 0012 2z"/>',
  code: '<path d="M9 8l-4 4 4 4M15 8l4 4-4 4"/>',
  eye: '<path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12z"/><circle cx="12" cy="12" r="2.5"/>',
  send: '<path d="M4 12l16-8-6 16-2.5-6z"/><path d="M11.5 14L20 4"/>',
  lock: '<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 018 0v3"/>',
};

export function icon(name, size = 16) {
  const body = ICONS[name] || "";
  return `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${body}</svg>`;
}
