import "./style.css";

const TOKEN_KEY = "gluekettle_token";
const LABELS = { cold: "冷锅", boiling: "熬煮中", drawn: "已出胶" };
const ROLE_LABELS = { admin: "管理员", worker: "操作工" };

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
  view: "board",
  board: null,
  alleys: [],
  picked: null,
  peak: "96",
  err: "",
  username: "admin",
  password: "123456",
};

function el(html) {
  const t = document.createElement("template");
  t.innerHTML = html.trim();
  return t.content.firstElementChild;
}

async function refresh() {
  const [board, alleys] = await Promise.all([api("/api/board"), api("/api/alleys")]);
  state.board = board;
  state.alleys = alleys.alleys;
  if (state.picked) {
    state.picked = state.board.kettles.find((k) => k.id === state.picked.id) || state.board.kettles[0];
  }
  render();
}

async function run(action) {
  state.err = "";
  try {
    await action();
    await refresh();
  } catch (ex) {
    state.err = ex.message;
    try {
      await refresh();
    } catch {
      render();
    }
  }
}

function alleyCfg(alley) {
  return state.alleys.find((a) => a.alley === alley);
}

function occText(alley) {
  const cfg = alleyCfg(alley);
  if (!cfg) return "";
  const note = !cfg.enabled ? " · 开关已关不限" : cfg.used >= cfg.cap ? " · 已满" : " · 可再拨";
  return `熬煮中并存 ${cfg.used}/${cfg.cap}${note}`;
}

function render() {
  app.innerHTML = "";
  if (!state.ready) {
    renderLogin();
    return;
  }
  const box = el(`<div>
    <nav class="topbar">
      <span class="brand">骨巷熬胶坊</span>
      <button class="nav ${state.view === "board" ? "on" : ""}" data-view="board">锅位作业台</button>
      <button class="nav ${state.view === "alleys" ? "on" : ""}" data-view="alleys">巷口并存</button>
      <span class="who">${state.user ? `${state.user.username} · ${ROLE_LABELS[state.user.role] || state.user.role}` : ""}</span>
      <button id="logout">退出</button>
    </nav>
    <div class="wrap"></div>
  </div>`);
  box.querySelectorAll("[data-view]").forEach((b) => {
    b.onclick = () => {
      state.view = b.dataset.view;
      state.err = "";
      refresh().catch((e) => {
        state.err = e.message;
        render();
      });
    };
  });
  box.querySelector("#logout").onclick = () => {
    localStorage.removeItem(TOKEN_KEY);
    Object.assign(state, { ready: false, user: null, board: null, alleys: [], picked: null, err: "" });
    render();
  };
  app.append(box);
  const wrap = box.querySelector(".wrap");
  if (!state.board) {
    wrap.append(el(`<div>${state.err || "装载锅位…"}</div>`));
    return;
  }
  if (state.view === "alleys") {
    renderAlleys(wrap);
  } else {
    renderBoard(wrap);
  }
  if (state.err) wrap.append(el(`<p class="err">${state.err}</p>`));
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

function renderBoard(wrap) {
  wrap.append(el(`<h1>${state.board.workshop}</h1>
    <p>${state.board.alley} · 点锅登记峰值；出胶须最近峰值 ≥ 90℃</p>`));
  const byAlley = new Map();
  state.board.kettles.forEach((k) => {
    const key = k.alley || "未分巷";
    if (!byAlley.has(key)) byAlley.set(key, []);
    byAlley.get(key).push(k);
  });
  const order = state.alleys.map((a) => a.alley).filter((a) => byAlley.has(a));
  byAlley.forEach((_, a) => {
    if (!order.includes(a)) order.push(a);
  });
  order.forEach((alley) => {
    const section = el(`<section class="alley-sec">
      <h2>${alley} <small>${occText(alley)}</small></h2>
      <div class="row"></div>
    </section>`);
    const row = section.querySelector(".row");
    byAlley.get(alley).forEach((k) => {
      const btn = el(`<button class="kettle ${k.status}"><strong>${k.code}</strong><span>${LABELS[k.status]}</span></button>`);
      btn.onclick = () => {
        state.picked = k;
        render();
      };
      row.append(btn);
    });
    wrap.append(section);
  });
  wrap.append(el(`<section class="drawer"></section>`));
  if (state.picked) {
    renderDrawer(wrap.querySelector(".drawer"));
  }
}

function renderDrawer(d) {
  const k = state.picked;
  d.innerHTML = `<h3>${k.code} · ${LABELS[k.status]}</h3>
    <p>${k.alley} · ${occText(k.alley)}</p>
    <p>最近峰值：${k.latestPeakC ?? "无"} ℃ · ${k.cookCount} 次</p>
    <input id="peak" value="${state.peak}" />
    <button id="log">登记峰值</button>
    <div>
      <button data-s="cold">冷锅</button>
      <button data-s="boiling">熬煮中</button>
      <button data-s="drawn">已出胶</button>
    </div>`;
  d.querySelector("#log").onclick = () =>
    run(async () => {
      state.peak = d.querySelector("#peak").value;
      state.picked = await api(`/api/kettles/${k.id}/cooks`, {
        method: "POST",
        body: JSON.stringify({ peakTempC: Number(state.peak) }),
      });
    });
  d.querySelectorAll("[data-s]").forEach((b) => {
    b.onclick = () =>
      run(async () => {
        state.picked = await api(`/api/kettles/${k.id}/status`, {
          method: "POST",
          body: JSON.stringify({ status: b.dataset.s }),
        });
      });
  });
}

function renderAlleys(wrap) {
  const isAdmin = state.user && state.user.role === "admin";
  wrap.append(el(`<h1>巷口并存</h1>
    <p>每巷熬煮中并存上限与启用开关；当前占用为该巷真实熬煮中锅数。${isAdmin ? "" : "操作工只读，仅管理员可改。"}</p>`));
  const grid = el(`<div class="alley-grid"></div>`);
  state.alleys.forEach((a) => {
    const full = a.enabled && a.used >= a.cap;
    const card = el(`<section class="alley-card ${full ? "full" : ""}">
      <h3>${a.alley}</h3>
      <p class="occ">当前占用：<strong>${a.used}</strong> / ${a.cap} 口
        <span class="badge">${a.enabled ? (full ? "已满" : "可再拨") : "开关已关"}</span>
      </p>
    </section>`);
    if (isAdmin) {
      const form = el(`<div class="cfg">
        <label>上限（口）
          <input type="number" min="1" step="1" value="${a.cap}" data-cap />
        </label>
        <label class="chk">
          <input type="checkbox" ${a.enabled ? "checked" : ""} data-en /> 启用并存上限
        </label>
        <button data-save>保存</button>
      </div>`);
      form.querySelector("[data-save]").onclick = () =>
        run(async () => {
          await api(`/api/alleys/${encodeURIComponent(a.alley)}`, {
            method: "PUT",
            body: JSON.stringify({
              cap: Number(form.querySelector("[data-cap]").value),
              enabled: form.querySelector("[data-en]").checked,
            }),
          });
        });
      card.append(form);
    } else {
      card.append(el(`<p>上限：${a.cap} 口 · 开关：${a.enabled ? "开" : "关"}</p>`));
    }
    grid.append(card);
  });
  wrap.append(grid);
}

if (state.ready) {
  (async () => {
    try {
      state.user = await api("/api/auth/me");
      await refresh();
    } catch (e) {
      localStorage.removeItem(TOKEN_KEY);
      state.ready = false;
      state.err = e.message;
      render();
    }
  })();
} else {
  render();
}
