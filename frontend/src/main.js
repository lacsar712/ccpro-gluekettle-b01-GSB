import "./style.css";

const TOKEN_KEY = "gluekettle_token";
const LABELS = { cold: "冷锅", boiling: "熬煮中", drawn: "已出胶" };

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (options.body) headers["Content-Type"] = "application/json";
  const t = localStorage.getItem(TOKEN_KEY);
  if (t) headers.Authorization = `Bearer ${t}`;
  const res = await fetch(path, { ...options, headers });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || "请求失败");
  return data;
}

const app = document.getElementById("app");
const state = {
  ready: Boolean(localStorage.getItem(TOKEN_KEY)),
  user: null,
  board: null,
  pickedId: null,
  peak: "96",
  err: "",
  info: "",
  username: "admin",
  password: "123456",
};

function el(html) {
  const t = document.createElement("template");
  t.innerHTML = html.trim();
  return t.content.firstElementChild;
}

function view() {
  return location.hash === "#/alleys" ? "alleys" : "board";
}

window.addEventListener("hashchange", render);

async function refresh() {
  state.board = await api("/api/board");
  render();
}

function alleyMap() {
  const map = new Map((state.board.alleys || []).map((a) => [a.alley, a]));
  const extra = [];
  for (const k of state.board.kettles) {
    if (!map.has(k.alley)) {
      map.set(k.alley, { alley: k.alley, cap: null, enabled: true, occupied: null });
      extra.push(k.alley);
    }
  }
  return { map, extra };
}

function renderTopbar() {
  const v = view();
  const bar = el(`<header class="topbar">
    <span class="brand">🫕 骨巷熬胶坊</span>
    <nav>
      <a href="#/board" class="${v === "board" ? "active" : ""}">锅位作业台</a>
      <a href="#/alleys" class="${v === "alleys" ? "active" : ""}">巷口并存</a>
    </nav>
    <span class="who">${state.user.username} · ${state.user.role === "admin" ? "管理员" : "操作工"}
      <button id="logout" class="linkbtn">退出</button>
    </span>
  </header>`);
  bar.querySelector("#logout").onclick = () => {
    localStorage.removeItem(TOKEN_KEY);
    location.hash = "";
    location.reload();
  };
  return bar;
}

function renderLogin() {
  const box = el(`<div class="wrap">
    <h1>骨巷熬胶坊</h1>
    <p>一排熬锅作业台，原生页面，无前端框架。</p>
    <form autocomplete="off">
      <label>用户名
        <input name="u" autocomplete="off" value="${state.username}" />
      </label>
      <label>密码
        <input name="p" type="password" autocomplete="off" value="${state.password}" />
      </label>
      <p class="hint">已预填 admin / 123456，另有 worker / 123456</p>
      <button>登录</button>
    </form>
    <p class="err">${state.err}</p>
  </div>`);
  box.querySelector("form").onsubmit = async (e) => {
    e.preventDefault();
    state.err = "";
    try {
      const data = await api("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({
          username: box.querySelector("[name=u]").value,
          password: box.querySelector("[name=p]").value,
        }),
      });
      localStorage.setItem(TOKEN_KEY, data.access_token);
      state.user = data.user;
      state.ready = true;
      await refresh();
    } catch (ex) {
      state.err = ex.message;
      render();
    }
  };
  app.append(box);
}

function renderBoard(box) {
  const page = el(`<div class="wrap">
    <h1>${state.board.workshop}</h1>
    <p>${state.board.alley} · 点锅登记峰值；出胶须最近峰值 ≥ 90℃；冷锅入煮受本巷并存上限约束</p>
    <div class="board"></div>
    <section class="drawer"></section>
    <p class="info">${state.info}</p>
    <p class="err">${state.err}</p>
  </div>`);
  const boardEl = page.querySelector(".board");
  const { map } = alleyMap();
  const alleyNames = (state.board.alleys || []).map((a) => a.alley);
  for (const name of alleyNames) {
    const info = map.get(name);
    const kettles = state.board.kettles.filter((k) => k.alley === name);
    const full = info.enabled && info.cap !== null && info.occupied >= info.cap;
    const sec = el(`<section class="alley-block">
      <h2>${name}
        <span class="tag ${info.enabled ? (full ? "tag-full" : "tag-on") : "tag-off"}">
          ${info.enabled ? (full ? `已满 ${info.occupied}/${info.cap}` : `占用 ${info.occupied}/${info.cap}`) : "已停用"}
        </span>
      </h2>
      <div class="row"></div>
    </section>`);
    const row = sec.querySelector(".row");
    kettles.forEach((k) => {
      const picked = state.pickedId === k.id;
      const btn = el(`<button class="kettle ${k.status} ${picked ? "picked" : ""}"><strong>${k.code}</strong><span>${LABELS[k.status]}</span></button>`);
      btn.onclick = () => {
        state.pickedId = k.id;
        state.err = "";
        state.info = "";
        render();
      };
      row.append(btn);
    });
    boardEl.append(sec);
  }

  const picked = state.board.kettles.find((k) => k.id === state.pickedId);
  if (picked) {
    const d = page.querySelector(".drawer");
    const info = map.get(picked.alley);
    const full =
      info &&
      info.enabled &&
      info.cap !== null &&
      info.occupied >= info.cap &&
      picked.status === "cold";
    d.innerHTML = `<h3>${picked.code} · ${picked.alley} · ${LABELS[picked.status]}</h3>
      <p>最近峰值：${picked.latestPeakC ?? "无"} ℃ · ${picked.cookCount} 次</p>
      ${full ? `<p class="warn">${picked.alley}熬煮中已达上限（${info.cap} 口），拨入煮会被挡住；关闭巷口开关后方可再拨。</p>` : ""}
      <input id="peak" value="${state.peak}" />
      <button id="log">登记峰值</button>
      <div>
        <button data-s="cold">冷锅</button>
        <button data-s="boiling">熬煮中</button>
        <button data-s="drawn">已出胶</button>
      </div>`;
    d.querySelector("#log").onclick = async () => {
      state.err = "";
      state.info = "";
      state.peak = d.querySelector("#peak").value;
      try {
        await api(`/api/kettles/${picked.id}/cooks`, {
          method: "POST",
          body: JSON.stringify({ peakTempC: Number(state.peak) }),
        });
        state.info = "峰值已登记（不占用巷口并存名额）";
      } catch (ex) {
        state.err = ex.message;
      }
      await refresh();
    };
    d.querySelectorAll("[data-s]").forEach((b) => {
      b.onclick = async () => {
        state.err = "";
        state.info = "";
        const buttons = d.querySelectorAll("[data-s]");
        buttons.forEach((x) => (x.disabled = true));
        try {
          await api(`/api/kettles/${picked.id}/status`, {
            method: "POST",
            body: JSON.stringify({ status: b.dataset.s }),
          });
          state.info = "状态已更新";
        } catch (ex) {
          // 界面不自行预判成败：以后端中文结论为准，无论成败都重新拉取真实库态
          state.err = ex.message;
        }
        await refresh();
      };
    });
  }
  box.append(page);
}

function renderAlleys(box) {
  const isAdmin = state.user.role === "admin";
  const page = el(`<div class="wrap">
    <h1>巷口并存</h1>
    <p>按巷设置「熬煮中」并存上限与启用开关。东巷、西巷分开计，互不影响。</p>
    <p class="info">${state.info}</p>
    <p class="err">${state.err}</p>
    <div class="alley-list"></div>
    ${isAdmin ? "" : `<p class="hint">操作工只读：上限与开关请联系管理员修改。</p>`}
  </div>`);
  const list = page.querySelector(".alley-list");
  (state.board.alleys || []).forEach((a) => {
    const full = a.enabled && a.occupied >= a.cap;
    const card = el(`<section class="alley-card">
      <h2>${a.alley}
        <span class="tag ${a.enabled ? (full ? "tag-full" : "tag-on") : "tag-off"}">
          ${a.enabled ? (full ? `已满 ${a.occupied}/${a.cap}` : `占用 ${a.occupied}/${a.cap}`) : "已停用"}
        </span>
      </h2>
      ${
        isAdmin
          ? `<form class="alley-form">
              <label>并存上限（正整数）
                <input name="cap" type="number" min="1" step="1" value="${a.cap}" />
              </label>
              <label class="switch-label">
                <input name="enabled" type="checkbox" ${a.enabled ? "checked" : ""} />
                启用上限开关
              </label>
              <button>保存</button>
              <span class="form-msg"></span>
            </form>`
          : `<ul class="readonly">
              <li>并存上限：<strong>${a.cap}</strong> 口</li>
              <li>开关：<strong>${a.enabled ? "开启" : "关闭"}</strong></li>
              <li>当前占用：<strong>${a.occupied}</strong> 口（真实熬煮中锅数）</li>
            </ul>`
      }
    </section>`);
    if (isAdmin) {
      const form = card.querySelector(".alley-form");
      form.onsubmit = async (e) => {
        e.preventDefault();
        const msg = card.querySelector(".form-msg");
        msg.textContent = "";
        const capRaw = Number(form.querySelector("[name=cap]").value);
        const enabled = form.querySelector("[name=enabled]").checked;
        if (!Number.isInteger(capRaw) || capRaw < 1) {
          state.err = "并存上限必须是正整数";
          render();
          return;
        }
        try {
          await api(`/api/alleys/${encodeURIComponent(a.alley)}`, {
            method: "PATCH",
            body: JSON.stringify({ cap: capRaw, enabled }),
          });
          state.err = "";
          state.info = `${a.alley}配置已保存`;
        } catch (ex) {
          state.err = ex.message;
        }
        await refresh();
      };
    }
    list.append(card);
  });
  box.append(page);
}

function render() {
  app.innerHTML = "";
  if (!state.ready || !state.user) {
    renderLogin();
    return;
  }
  app.append(renderTopbar());
  if (!state.board) {
    app.append(el(`<div class="wrap">${state.err || "装载锅位…"}</div>`));
    return;
  }
  if (view() === "alleys") {
    renderAlleys(app);
  } else {
    renderBoard(app);
  }
}

async function boot() {
  if (!state.ready) {
    render();
    return;
  }
  try {
    state.user = await api("/api/auth/me");
    await refresh();
  } catch (ex) {
    localStorage.removeItem(TOKEN_KEY);
    state.ready = false;
    state.user = null;
    state.err = ex.message;
    render();
  }
}

boot();
