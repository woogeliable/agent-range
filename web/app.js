import { api, esc, toast, icon, difficultyDots } from "./api.js";
import { mountLesson, unmountLesson } from "./lesson.js";

const app = document.getElementById("app");
const state = { me: null, course: null, routeToken: 0 };

/* ---------------- chrome ---------------- */
function renderChrome(me) {
  state.me = me;
  const score = document.getElementById("scoreChip");
  if (score) score.textContent = `${me.progress.score || 0} 分`;
  const model = document.getElementById("modelChip");
  if (model) {
    model.innerHTML = `<span class="dot"></span>${me.model && me.model.enabled ? "真实模型" : "模拟目标"}`;
    model.title = (me.model && me.model.message) || "";
  }
  const user = document.getElementById("userChip");
  if (user) {
    const handle = (me.user && me.user.handle) || "guest";
    user.textContent = handle.slice(0, 1).toUpperCase();
    user.title = `本地游客会话 · ${handle}`;
  }
}

async function refreshChrome() {
  try {
    const me = await api("/api/me");
    renderChrome(me);
  } catch (error) {
    /* keep the current chrome on transient errors */
  }
}

/* ---------------- routing ---------------- */
function navigate(path) {
  if (location.pathname !== path) {
    history.pushState({}, "", path);
  }
  route();
  window.scrollTo({ top: 0, behavior: "instant" in window ? "instant" : "auto" });
}

document.addEventListener("click", (event) => {
  const link = event.target.closest("a[data-link]");
  if (!link) return;
  if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
  const href = link.getAttribute("href");
  if (!href || href.startsWith("http")) return;
  event.preventDefault();
  navigate(href);
});

window.addEventListener("popstate", () => route());

function updateNav(path) {
  document.querySelectorAll(".nav-link[href]").forEach((node) => {
    const isCourse = path === "/" || path.startsWith("/lesson/");
    node.classList.toggle("is-active", isCourse && node.getAttribute("href") === "/");
  });
}

async function route() {
  const token = ++state.routeToken;
  unmountLesson();
  const path = location.pathname.replace(/\/+$/, "") || "/";
  updateNav(path);

  if (path === "/") {
    await renderCourse(token);
    return;
  }
  const lessonMatch = path.match(/^\/lesson\/([A-Za-z0-9._-]+)$/);
  if (lessonMatch) {
    mountLesson(app, lessonMatch[1], { refreshChrome });
    return;
  }
  app.innerHTML = `<div class="wrap"><div class="error-panel"><h2>页面不存在</h2><p>这个地址没有对应的靶场页面。</p><p><a class="btn btn-primary" href="/" data-link>返回课程地图</a></p></div></div>`;
}

/* ---------------- course map ---------------- */
function statBlock(value, label) {
  return `<div class="stat"><div class="stat-value">${esc(value)}</div><div class="stat-label">${esc(label)}</div></div>`;
}

function lessonCard(lesson) {
  const total = lesson.total_tasks || 0;
  const done = lesson.completed_tasks || 0;
  const pct = total ? Math.round((done * 100) / total) : 0;
  const status = lesson.done ? "done" : done > 0 ? "progress" : "";
  const statusLabel = lesson.done ? "已完成" : done > 0 ? "进行中" : "未开始";
  return `
    <a class="lesson-card ${lesson.done ? "is-done" : ""}" href="/lesson/${esc(lesson.id)}" data-link>
      <div class="lesson-card-top">
        <span class="lesson-id">${esc(lesson.id)}</span>
        <span class="status-chip ${status}">${statusLabel}</span>
      </div>
      <h3>${esc(lesson.title)}</h3>
      <p>${esc(lesson.subtitle)}</p>
      <div class="lesson-meta">
        ${difficultyDots(lesson.difficulty)}
        <span>${esc(lesson.minutes)} 分钟</span>
        <span>${done}/${total} 任务</span>
      </div>
      <div class="mini-bar"><i style="width:${pct}%"></i></div>
    </a>`;
}

function chapterBlock(chapter) {
  if (chapter.upcoming) {
    const planned = chapter.planned || [];
    return `
      <section class="chapter" id="chapter-${esc(chapter.id)}">
        <div class="chapter-head">
          <div class="chapter-index">${esc(chapter.id)}</div>
          <div class="chapter-info">
            <h2>${esc(chapter.title)}</h2>
            <p>${esc(chapter.summary)}</p>
          </div>
          <div class="chapter-progress"><strong>—</strong>规划中</div>
        </div>
        <div class="upcoming-grid">
          ${
            planned.length
              ? planned
                  .map(
                    (title) => `<div class="upcoming-card">
                      <h3>${esc(title)}</h3>
                      <p>本章暂未上线；编号保留，避免打乱课程体系。</p>
                    </div>`
                  )
                  .join("")
              : `<div class="upcoming-card"><h3>即将上线</h3><p>本章关卡将在后续版本加入。</p></div>`
          }
        </div>
      </section>`;
  }
  const lessons = chapter.lessons || [];
  const done = lessons.filter((item) => item.done).length;
  return `
    <section class="chapter" id="chapter-${esc(chapter.id)}">
      <div class="chapter-head">
        <div class="chapter-index">${esc(chapter.id)}</div>
        <div class="chapter-info">
          <h2>${esc(chapter.title)}</h2>
          <p>${esc(chapter.summary)}</p>
        </div>
        <div class="chapter-progress">
          <strong>${done}/${lessons.length}</strong>完成关卡
        </div>
      </div>
      <div class="lesson-grid">${lessons.map(lessonCard).join("")}</div>
    </section>`;
}

function heroArt() {
  return `
    <div class="hero-art" aria-hidden="true">
      <div class="term">
        <div class="term-head">
          <span class="term-dot red"></span><span class="term-dot amber"></span><span class="term-dot green"></span>
          <span class="term-title">attempt / trace</span>
        </div>
        <div class="term-body">
          <div class="term-line"><span class="t">context</span><span class="c"><span class="term-tag blue">system</span><span class="term-tag">user</span><span class="term-tag red">retrieval</span> 5 段</span></div>
          <div class="term-line"><span class="t">directive</span><span class="c">forum-post → set_fact(warranty=0)</span></div>
          <div class="term-line"><span class="t">policy</span><span class="c"><span class="bad">trust boundary missing</span></span></div>
          <div class="term-line"><span class="t">fact</span><span class="c">warranty_days <span class="bad">365 → 0</span></span></div>
          <div class="term-line"><span class="t">verifier</span><span class="c"><span class="ok">t1 passed ✓</span> 服务端证据</span></div>
          <div class="term-line"><span class="t">answer</span><span class="c">“保修期是 0 天。”</span></div>
        </div>
        <div class="term-foot"><span>SIMULATED · LOCAL</span><span>no egress</span></div>
      </div>
    </div>`;
}

async function renderCourse(token) {
  app.innerHTML = `<div class="boot"><div class="boot-mark">AR</div><p>正在装载课程地图…</p></div>`;
  let data;
  try {
    data = await api("/api/lessons");
  } catch (error) {
    if (token !== state.routeToken) return;
    app.innerHTML = `<div class="wrap"><div class="error-panel"><h2>无法加载课程</h2><p>${esc(error.message)}</p><button class="btn btn-primary" id="retry">重新加载</button></div></div>`;
    document.getElementById("retry").onclick = () => renderCourse(state.routeToken);
    return;
  }
  if (token !== state.routeToken) return;
  state.course = data;

  const progress = data.progress || {};
  const allLessons = data.chapters.reduce((acc, chapter) => acc.concat(chapter.lessons || []), []);
  const next = allLessons.find((lesson) => !lesson.done) || allLessons[0];
  const cta = progress.tasks_done ? "继续下一关" : "从第一关开始";

  app.innerHTML = `
    <div class="wrap">
      <section class="hero">
        <div class="hero-copy">
          <p class="eyebrow">AI APPLICATION SECURITY RANGE</p>
          <h1 class="hero-title">像打靶场一样，<br>学会 <span class="accent">AI 应用安全</span>。</h1>
          <p class="hero-lead">
            不是看 Demo，而是亲手打穿一条真实的上下文流水线：<strong>检索文档 → 模型决策 → 工具调用 → 下游副作用</strong>。
            每一关都有任务、提示、源码和四档防御；每一次成败都由服务端证据判定。
          </p>
          <div class="hero-actions">
            <a class="btn btn-primary" href="${next ? `/lesson/${esc(next.id)}` : "/"}" data-link>
              ${icon("play")} ${cta}
            </a>
            <a class="btn" href="#course">浏览课程地图 ${icon("arrow")}</a>
          </div>
          <div class="hero-stats">
            ${statBlock(`${progress.lessons_done || 0}/${progress.lessons_total || 0}`, "完成关卡")}
            ${statBlock(`${progress.tasks_done || 0}/${progress.tasks_total || 0}`, "完成任务")}
            ${statBlock(progress.score || 0, "当前得分")}
          </div>
        </div>
        ${heroArt()}
      </section>

      <section class="quickstart" aria-label="90 秒上手">
        <div class="quickstart-head">
          <h2>90 秒上手</h2>
          <span>NO SETUP · NO LOGIN · LOCAL ONLY</span>
        </div>
        <div class="steps">
          <div class="step"><span class="step-num">1</span><div><h3>打开即玩</h3><p>游客会话自动创建。没有环境变量，没有注册，没有令牌粘贴。</p></div></div>
          <div class="step"><span class="step-num">2</span><div><h3>先攻破，再修</h3><p>同一句 payload，切到加固档看它在哪一层被拦。<code>View Source</code> 给源码。</p></div></div>
          <div class="step"><span class="step-num">3</span><div><h3>用证据判定</h3><p>金丝雀、工具调用、世界状态——模型说“已执行”不算数。</p></div></div>
        </div>
      </section>

      <div id="course">
        <p class="course-note">
          编号采用「章.关」：第 4、5 章已全部上线（4.1–4.3、5.1–5.3）；第 1.5、2.3–2.4、3.4–3.7、6–7 章仍规划中。
        </p>
        ${data.chapters.map(chapterBlock).join("")}
      </div>

      <footer class="footer">
        <div>
          <strong>AgentRange 3.2</strong> · AI 应用安全靶场<br>
          本地优先 · 默认零外网 · 所有实体、订单与文档均为虚构数据
        </div>
        <div>
          当前交付：17 关（P1–P3 + 第 4–5 章）<br>
          研究台 P4 · 其余规划关卡与发布 P5
        </div>
      </footer>
    </div>`;

  refreshChrome();
}

/* ---------------- boot ---------------- */
async function boot() {
  try {
    const me = await api("/api/me");
    renderChrome(me);
  } catch (error) {
    app.innerHTML = `<div class="wrap"><div class="error-panel"><h2>靶场没有响应</h2><p>${esc(error.message)}</p><p>请确认 <code>python3 server.py</code> 仍在运行，然后刷新页面。</p><button class="btn btn-primary" id="bootRetry">刷新</button></div></div>`;
    const retry = document.getElementById("bootRetry");
    if (retry) retry.addEventListener("click", () => location.reload());
    return;
  }
  route();
}

boot();
