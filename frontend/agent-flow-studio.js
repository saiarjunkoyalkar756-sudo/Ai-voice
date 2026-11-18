/**
 * Voicely Agent Flow Studio — visual call-flow builder
 * Dograh-style node graph · Voicely brand · vanilla JS (no React)
 *
 * Public API:
 *   VoicelyFlowStudio.mount(container, { sections, onChange, agentName })
 *   VoicelyFlowStudio.getSections(instance)
 *   VoicelyFlowStudio.destroy(instance)
 */
(function (global) {
  "use strict";

  const NODE_TYPES = {
    start: { label: "Start Call", badge: "Start" },
    global: { label: "Global Rules", badge: "Global" },
    agent: { label: "Agenda Step", badge: "Agent" },
    end: { label: "End Call", badge: "End" },
  };

  function uid(prefix) {
    return `${prefix}_${Math.random().toString(36).slice(2, 9)}`;
  }

  function esc(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function defaultGraph(agentName) {
    const start = {
      id: "start_call",
      title: "Start Call",
      content:
        "# OPENING\n- Greet the caller warmly.\n- State who you are and why you're calling (if outbound).\n- Earn 20–30 seconds of attention — don't dump everything.",
      enabled: true,
      order: 1,
      node_type: "start",
      position_x: 280,
      position_y: 40,
      transitions: [{ to: "main_agenda", label: "Move to agenda", condition: "" }],
    };
    const global = {
      id: "global_rules",
      title: "Global Node",
      content:
        "# ALWAYS REMEMBER\n- Stay on brand for Voicely.\n- 1–2 sentences, then a question.\n- Never claim to be human if asked — deflect with identity shield style.\n- End call only when the goal is done or the caller insists.",
      enabled: true,
      order: 0,
      node_type: "global",
      position_x: 40,
      position_y: 200,
      transitions: [],
    };
    const main = {
      id: "main_agenda",
      title: "Main Agenda",
      content:
        "# MAIN ACTION\n- Discover needs and budget.\n- Match inventory / offer.\n- Handle objections briefly.\n- Drive toward site visit or next step.",
      enabled: true,
      order: 2,
      node_type: "agent",
      position_x: 520,
      position_y: 220,
      transitions: [{ to: "end_call", label: "End call", condition: "" }],
    };
    const end = {
      id: "end_call",
      title: "End Call",
      content:
        "# CLOSE\n- Summarize the next step.\n- Confirm WhatsApp / callback if needed.\n- Warm goodbye. Do not start new topics.",
      enabled: true,
      order: 3,
      node_type: "end",
      position_x: 280,
      position_y: 420,
      transitions: [],
    };
    return [global, start, main, end];
  }

  function normalizeSections(sections, agentName) {
    let list = Array.isArray(sections) ? sections.map((s, i) => ({ ...s })) : [];
    if (!list.length) list = defaultGraph(agentName);
    // Ensure positions for legacy list-only flows
    list = list.map((s, i) => {
      const node_type = s.node_type || (i === 0 ? "start" : i === list.length - 1 ? "end" : "agent");
      return {
        id: s.id || uid("node"),
        title: s.title || NODE_TYPES[node_type]?.label || `Step ${i + 1}`,
        content: s.content || "",
        enabled: s.enabled !== false,
        order: Number(s.order) || i + 1,
        node_type,
        position_x: Number(s.position_x) || 80 + (i % 3) * 280,
        position_y: Number(s.position_y) || 60 + Math.floor(i / 3) * 180,
        transitions: Array.isArray(s.transitions)
          ? s.transitions.map((t) => ({
              to: t.to || t.target || "",
              label: t.label || "",
              condition: t.condition || "",
            }))
          : [],
      };
    });
    // Auto-chain if no transitions at all (legacy linear sections)
    const anyEdge = list.some((s) => (s.transitions || []).length);
    if (!anyEdge && list.length > 1) {
      const ordered = [...list].sort((a, b) => a.order - b.order);
      for (let i = 0; i < ordered.length - 1; i++) {
        if (ordered[i].node_type === "global") continue;
        ordered[i].transitions = [
          { to: ordered[i + 1].id, label: "Next", condition: "" },
        ];
      }
    }
    return list;
  }

  function mount(container, opts) {
    if (!container) throw new Error("VoicelyFlowStudio: container required");
    const options = opts || {};
    const state = {
      sections: normalizeSections(options.sections, options.agentName),
      selectedId: null,
      scale: 1,
      panX: 40,
      panY: 30,
      drag: null,
      connect: null,
      dirty: false,
      chat: [],
      rail: "inspect",
      onChange: typeof options.onChange === "function" ? options.onChange : null,
      agentName: options.agentName || "Agent",
    };

    container.classList.add("sfs-root");
    container.innerHTML = `
      <div class="sfs-shell">
        <div class="sfs-main">
          <div class="sfs-toolbar">
            <span class="sfs-title">Call flow</span>
            <span class="sfs-sub">Visual stages · Voicely Studio</span>
            <span class="sfs-badge draft" data-sfs-badge>Draft</span>
            <button type="button" class="btn btn-secondary btn-sm" data-sfs-act="add-agent">+ Agenda</button>
            <button type="button" class="btn btn-secondary btn-sm" data-sfs-act="add-global">+ Global</button>
            <button type="button" class="btn btn-primary btn-sm btn-voicely" data-sfs-act="save">Save flow</button>
          </div>
          <div class="sfs-canvas-wrap" data-sfs-canvas>
            <div class="sfs-world" data-sfs-world>
              <svg class="sfs-edges" data-sfs-edges></svg>
              <div data-sfs-nodes></div>
            </div>
            <div class="sfs-zoom">
              <button type="button" data-sfs-act="zoom-out" title="Zoom out">−</button>
              <button type="button" data-sfs-act="zoom-reset" title="Reset">⟲</button>
              <button type="button" data-sfs-act="zoom-in" title="Zoom in">+</button>
            </div>
            <div class="sfs-fab">
              <button type="button" data-sfs-act="add-agent" title="Add agenda step">+</button>
            </div>
          </div>
        </div>
        <aside class="sfs-rail">
          <div class="sfs-rail-tabs">
            <button type="button" class="on" data-sfs-rail="inspect">Inspector</button>
            <button type="button" data-sfs-rail="test">Test chat</button>
          </div>
          <div class="sfs-rail-body" data-sfs-rail-body></div>
        </aside>
      </div>
    `;

    const els = {
      canvas: container.querySelector("[data-sfs-canvas]"),
      world: container.querySelector("[data-sfs-world]"),
      edges: container.querySelector("[data-sfs-edges]"),
      nodes: container.querySelector("[data-sfs-nodes]"),
      railBody: container.querySelector("[data-sfs-rail-body]"),
      badge: container.querySelector("[data-sfs-badge]"),
    };

    function emit() {
      state.dirty = true;
      if (els.badge) {
        els.badge.textContent = "Unsaved";
        els.badge.classList.add("draft");
      }
      if (state.onChange) state.onChange(getSections());
    }

    function getSections() {
      return state.sections.map((s, i) => ({
        id: s.id,
        title: s.title,
        content: s.content,
        enabled: s.enabled !== false,
        order: i + 1,
        node_type: s.node_type || "agent",
        position_x: s.position_x,
        position_y: s.position_y,
        transitions: (s.transitions || []).map((t) => ({
          to: t.to,
          label: t.label || "",
          condition: t.condition || "",
        })),
      }));
    }

    function nodeById(id) {
      return state.sections.find((s) => s.id === id);
    }

    function applyTransform() {
      els.world.style.transform = `translate(${state.panX}px, ${state.panY}px) scale(${state.scale})`;
    }

    function portCenter(node, which) {
      const w = 260;
      const h = 120;
      const x = node.position_x + (which === "out" ? w : 0);
      const y = node.position_y + h / 2;
      return { x, y };
    }

    function renderEdges() {
      const parts = [];
      const idMap = Object.fromEntries(state.sections.map((s) => [s.id, s]));
      state.sections.forEach((from) => {
        (from.transitions || []).forEach((tr, ti) => {
          const to = idMap[tr.to];
          if (!to) return;
          const a = portCenter(from, "out");
          const b = portCenter(to, "in");
          const dx = Math.max(40, Math.abs(b.x - a.x) * 0.45);
          const d = `M ${a.x} ${a.y} C ${a.x + dx} ${a.y}, ${b.x - dx} ${b.y}, ${b.x} ${b.y}`;
          const midX = (a.x + b.x) / 2;
          const midY = (a.y + b.y) / 2;
          const label = tr.label || "next";
          parts.push(
            `<path class="sfs-edge" data-from="${esc(from.id)}" data-ti="${ti}" d="${d}" />` +
              (label
                ? `<rect class="sfs-edge-label-bg" x="${midX - 28}" y="${midY - 9}" width="56" height="16" rx="4"/>` +
                  `<text class="sfs-edge-label" x="${midX}" y="${midY + 3}" text-anchor="middle">${esc(label.slice(0, 14))}</text>`
                : "")
          );
        });
      });
      if (state.connect && state.connect.mx != null) {
        const from = nodeById(state.connect.fromId);
        if (from) {
          const a = portCenter(from, "out");
          const b = { x: state.connect.mx, y: state.connect.my };
          const dx = Math.max(40, Math.abs(b.x - a.x) * 0.4);
          parts.push(
            `<path class="sfs-edge-temp" d="M ${a.x} ${a.y} C ${a.x + dx} ${a.y}, ${b.x - dx} ${b.y}, ${b.x} ${b.y}" />`
          );
        }
      }
      els.edges.innerHTML = parts.join("");
      // Size SVG large enough
      els.edges.setAttribute("width", "4000");
      els.edges.setAttribute("height", "3000");
      els.edges.style.width = "4000px";
      els.edges.style.height = "3000px";
    }

    function renderNodes() {
      els.nodes.innerHTML = state.sections
        .map((n) => {
          const type = n.node_type || "agent";
          const preview = (n.content || "").replace(/#+\s*/g, "").trim().slice(0, 140);
          const showIn = type !== "start" && type !== "global";
          const showOut = type !== "end" && type !== "global";
          return `
            <div class="sfs-node ${state.selectedId === n.id ? "selected" : ""}"
                 data-id="${esc(n.id)}" data-type="${esc(type)}"
                 style="left:${n.position_x}px;top:${n.position_y}px">
              <div class="sfs-node-head">
                <span class="sfs-node-type">${esc(NODE_TYPES[type]?.badge || type)}</span>
                <span class="sfs-node-title">${esc(n.title)}</span>
              </div>
              <div class="sfs-node-body">
                <strong>Prompt</strong>
                ${esc(preview || "Empty stage instructions…")}
              </div>
              ${showIn ? `<div class="sfs-port in" data-port="in" data-id="${esc(n.id)}"></div>` : ""}
              ${showOut ? `<div class="sfs-port out" data-port="out" data-id="${esc(n.id)}"></div>` : ""}
            </div>`;
        })
        .join("");
    }

    function renderRail() {
      if (state.rail === "test") {
        els.railBody.innerHTML = `
          <div class="sfs-chat">
            <h4>Test chat</h4>
            <p class="muted">Simulate stage prompts offline. Live voice uses the same flow sections as system guidance.</p>
            <div class="sfs-chat-log" data-sfs-chat-log>
              ${state.chat
                .map(
                  (m) =>
                    `<div class="sfs-chat-bubble ${m.role}">${esc(m.text)}</div>`
                )
                .join("") ||
                `<div class="muted" style="padding:12px">Say hello to walk the Start → Agenda path.</div>`}
            </div>
            <div class="sfs-chat-input-row">
              <input type="text" placeholder="Type as caller…" data-sfs-chat-input />
              <button type="button" class="btn btn-primary btn-sm btn-voicely" data-sfs-act="chat-send">Send</button>
            </div>
            <button type="button" class="sfs-run-btn" data-sfs-act="chat-run">▶ Run stage walkthrough</button>
          </div>`;
        return;
      }

      const n = nodeById(state.selectedId);
      if (!n) {
        els.railBody.innerHTML = `
          <div class="sfs-empty-inspector">
            <div class="ico">◇</div>
            <h4>Select a stage</h4>
            <p class="muted">Click a node to edit prompts, transitions, and enable/disable stages. Drag ports to connect the call path.</p>
          </div>`;
        return;
      }

      const typeOpts = Object.keys(NODE_TYPES)
        .map(
          (k) =>
            `<option value="${k}" ${n.node_type === k ? "selected" : ""}>${NODE_TYPES[k].label}</option>`
        )
        .join("");
      const targets = state.sections
        .filter((s) => s.id !== n.id && s.node_type !== "global")
        .map(
          (s) =>
            `<option value="${esc(s.id)}">${esc(s.title)}</option>`
        )
        .join("");
      const edges = (n.transitions || [])
        .map(
          (t, i) => `
          <div class="sfs-field" style="border:1px solid rgba(255,255,255,.06);padding:8px;border-radius:8px">
            <span>Transition ${i + 1}</span>
            <select data-sfs-edge-to="${i}">${state.sections
              .filter((s) => s.id !== n.id)
              .map(
                (s) =>
                  `<option value="${esc(s.id)}" ${t.to === s.id ? "selected" : ""}>${esc(s.title)}</option>`
              )
              .join("")}</select>
            <input style="margin-top:6px" data-sfs-edge-label="${i}" value="${esc(t.label || "")}" placeholder="Label e.g. End call" />
            <button type="button" class="sfs-danger" data-sfs-edge-del="${i}" style="margin-top:6px">Remove edge</button>
          </div>`
        )
        .join("");

      els.railBody.innerHTML = `
        <h4>${esc(n.title)}</h4>
        <p class="muted">Stage instructions become call guidance for the Voicely voice engine.</p>
        <label class="sfs-field"><span>Title</span>
          <input data-sfs-field="title" value="${esc(n.title)}" /></label>
        <label class="sfs-field"><span>Type</span>
          <select data-sfs-field="node_type">${typeOpts}</select></label>
        <label class="sfs-field"><span>Prompt / stage brief</span>
          <textarea data-sfs-field="content">${esc(n.content)}</textarea></label>
        <label class="check-row" style="display:flex;gap:8px;align-items:center;margin-bottom:12px;color:#c5d9ce;font-size:13px">
          <input type="checkbox" data-sfs-field="enabled" ${n.enabled !== false ? "checked" : ""} />
          Stage enabled
        </label>
        <h4 style="margin-top:8px;font-size:12px;color:#7a9588;text-transform:uppercase;letter-spacing:.06em">Transitions</h4>
        ${edges || `<p class="muted">No outgoing edges — drag the green port to another node.</p>`}
        <label class="sfs-field"><span>Add edge to</span>
          <select data-sfs-add-edge>${targets}</select></label>
        <button type="button" class="btn btn-secondary btn-sm" data-sfs-act="add-edge" style="width:100%">Add transition</button>
        <button type="button" class="sfs-danger" data-sfs-act="delete-node">Delete stage</button>
      `;
    }

    function render() {
      renderNodes();
      renderEdges();
      renderRail();
      applyTransform();
    }

    function select(id) {
      state.selectedId = id;
      render();
    }

    function addNode(type) {
      const id = uid(type);
      const n = {
        id,
        title: NODE_TYPES[type]?.label || "Stage",
        content: type === "global" ? "# GLOBAL RULES\n- " : "# STAGE\n- ",
        enabled: true,
        order: state.sections.length + 1,
        node_type: type,
        position_x: 200 + state.sections.length * 20,
        position_y: 160 + state.sections.length * 16,
        transitions: [],
      };
      state.sections.push(n);
      select(id);
      emit();
    }

    function deleteNode(id) {
      const n = nodeById(id);
      if (!n) return;
      if (n.node_type === "start" || n.node_type === "end") {
        if (typeof showToast === "function")
          showToast("Keep Start and End stages — edit them instead", "error");
        return;
      }
      state.sections = state.sections.filter((s) => s.id !== id);
      state.sections.forEach((s) => {
        s.transitions = (s.transitions || []).filter((t) => t.to !== id);
      });
      if (state.selectedId === id) state.selectedId = null;
      render();
      emit();
    }

    function clientToWorld(clientX, clientY) {
      const rect = els.canvas.getBoundingClientRect();
      const x = (clientX - rect.left - state.panX) / state.scale;
      const y = (clientY - rect.top - state.panY) / state.scale;
      return { x, y };
    }

    // ── events ─────────────────────────────────────────────────
    container.addEventListener("click", (e) => {
      const act = e.target.closest("[data-sfs-act]")?.getAttribute("data-sfs-act");
      if (act === "add-agent") addNode("agent");
      if (act === "add-global") addNode("global");
      if (act === "zoom-in") {
        state.scale = Math.min(1.6, state.scale + 0.1);
        applyTransform();
      }
      if (act === "zoom-out") {
        state.scale = Math.max(0.45, state.scale - 0.1);
        applyTransform();
      }
      if (act === "zoom-reset") {
        state.scale = 1;
        state.panX = 40;
        state.panY = 30;
        applyTransform();
      }
      if (act === "save") {
        state.dirty = false;
        if (els.badge) {
          els.badge.textContent = "Saved";
          els.badge.classList.remove("draft");
        }
        if (state.onChange) state.onChange(getSections());
        if (typeof showToast === "function") showToast("Flow ready — click Save Changes on the agent", "ok");
      }
      if (act === "delete-node" && state.selectedId) deleteNode(state.selectedId);
      if (act === "add-edge" && state.selectedId) {
        const sel = container.querySelector("[data-sfs-add-edge]");
        const n = nodeById(state.selectedId);
        if (n && sel?.value) {
          n.transitions = n.transitions || [];
          n.transitions.push({ to: sel.value, label: "Next", condition: "" });
          render();
          emit();
        }
      }
      if (act === "chat-send" || act === "chat-run") {
        const input = container.querySelector("[data-sfs-chat-input]");
        const text =
          act === "chat-run"
            ? "Hello — walk me through the call stages"
            : (input?.value || "").trim();
        if (!text && act !== "chat-run") return;
        if (input) input.value = "";
        state.chat.push({ role: "user", text: text || "Hello" });
        const start = state.sections.find((s) => s.node_type === "start") || state.sections[0];
        const agenda =
          state.sections.find((s) => s.node_type === "agent") ||
          state.sections.find((s) => s.id !== start?.id);
        const reply = [
          `【${start?.title || "Start"}】 ${(start?.content || "").replace(/#+\s*/g, " ").trim().slice(0, 160)}`,
          agenda
            ? `【${agenda.title}】 ${(agenda.content || "").replace(/#+\s*/g, " ").trim().slice(0, 160)}`
            : "",
        ]
          .filter(Boolean)
          .join("\n\n");
        state.chat.push({
          role: "agent",
          text: reply || "Configure stage prompts on the canvas to preview guidance.",
        });
        renderRail();
        const log = container.querySelector("[data-sfs-chat-log]");
        if (log) log.scrollTop = log.scrollHeight;
      }

      const rail = e.target.closest("[data-sfs-rail]")?.getAttribute("data-sfs-rail");
      if (rail) {
        state.rail = rail;
        container.querySelectorAll("[data-sfs-rail]").forEach((b) => {
          b.classList.toggle("on", b.getAttribute("data-sfs-rail") === rail);
        });
        renderRail();
      }

      const edgeDel = e.target.closest("[data-sfs-edge-del]");
      if (edgeDel && state.selectedId) {
        const n = nodeById(state.selectedId);
        const idx = Number(edgeDel.getAttribute("data-sfs-edge-del"));
        if (n) {
          n.transitions.splice(idx, 1);
          render();
          emit();
        }
      }
    });

    container.addEventListener("input", (e) => {
      const field = e.target.getAttribute("data-sfs-field");
      if (field && state.selectedId) {
        const n = nodeById(state.selectedId);
        if (!n) return;
        if (field === "enabled") n.enabled = e.target.checked;
        else n[field] = e.target.value;
        if (field === "title" || field === "node_type") renderNodes();
        emit();
      }
      const et = e.target.getAttribute("data-sfs-edge-to");
      if (et != null && state.selectedId) {
        const n = nodeById(state.selectedId);
        if (n?.transitions?.[Number(et)]) {
          n.transitions[Number(et)].to = e.target.value;
          renderEdges();
          emit();
        }
      }
      const el = e.target.getAttribute("data-sfs-edge-label");
      if (el != null && state.selectedId) {
        const n = nodeById(state.selectedId);
        if (n?.transitions?.[Number(el)]) {
          n.transitions[Number(el)].label = e.target.value;
          renderEdges();
          emit();
        }
      }
    });

    els.canvas.addEventListener("pointerdown", (e) => {
      const port = e.target.closest(".sfs-port");
      if (port) {
        e.stopPropagation();
        const id = port.getAttribute("data-id");
        const which = port.getAttribute("data-port");
        if (which === "out") {
          const w = clientToWorld(e.clientX, e.clientY);
          state.connect = { fromId: id, mx: w.x, my: w.y };
          els.canvas.classList.add("is-connecting");
          els.canvas.setPointerCapture(e.pointerId);
        }
        return;
      }
      const nodeEl = e.target.closest(".sfs-node");
      if (nodeEl) {
        e.stopPropagation();
        const id = nodeEl.getAttribute("data-id");
        select(id);
        const n = nodeById(id);
        const w = clientToWorld(e.clientX, e.clientY);
        state.drag = {
          id,
          ox: w.x - n.position_x,
          oy: w.y - n.position_y,
        };
        nodeEl.classList.add("is-dragging");
        els.canvas.setPointerCapture(e.pointerId);
        return;
      }
      // pan
      state.drag = { pan: true, x: e.clientX - state.panX, y: e.clientY - state.panY };
      els.canvas.classList.add("is-panning");
      els.canvas.setPointerCapture(e.pointerId);
    });

    els.canvas.addEventListener("pointermove", (e) => {
      if (state.connect) {
        const w = clientToWorld(e.clientX, e.clientY);
        state.connect.mx = w.x;
        state.connect.my = w.y;
        renderEdges();
        return;
      }
      if (!state.drag) return;
      if (state.drag.pan) {
        state.panX = e.clientX - state.drag.x;
        state.panY = e.clientY - state.drag.y;
        applyTransform();
        return;
      }
      const n = nodeById(state.drag.id);
      if (!n) return;
      const w = clientToWorld(e.clientX, e.clientY);
      n.position_x = Math.round(w.x - state.drag.ox);
      n.position_y = Math.round(w.y - state.drag.oy);
      const el = els.nodes.querySelector(`[data-id="${n.id}"]`);
      if (el) {
        el.style.left = `${n.position_x}px`;
        el.style.top = `${n.position_y}px`;
      }
      renderEdges();
    });

    els.canvas.addEventListener("pointerup", (e) => {
      if (state.connect) {
        const target = document.elementFromPoint(e.clientX, e.clientY);
        const portIn = target?.closest?.('.sfs-port[data-port="in"]');
        const nodeEl = target?.closest?.(".sfs-node");
        const toId =
          portIn?.getAttribute("data-id") || nodeEl?.getAttribute("data-id");
        const from = nodeById(state.connect.fromId);
        if (from && toId && toId !== from.id) {
          from.transitions = from.transitions || [];
          if (!from.transitions.some((t) => t.to === toId)) {
            from.transitions.push({ to: toId, label: "Next", condition: "" });
            emit();
          }
        }
        state.connect = null;
        els.canvas.classList.remove("is-connecting");
        render();
      }
      if (state.drag && !state.drag.pan) emit();
      state.drag = null;
      els.canvas.classList.remove("is-panning");
      els.nodes.querySelectorAll(".is-dragging").forEach((el) => el.classList.remove("is-dragging"));
    });

    // initial select start node
    const start = state.sections.find((s) => s.node_type === "start");
    state.selectedId = start?.id || state.sections[0]?.id || null;
    render();

    return {
      getSections,
      setSections(sections) {
        state.sections = normalizeSections(sections, state.agentName);
        render();
      },
      destroy() {
        container.innerHTML = "";
      },
      _state: state,
    };
  }

  global.VoicelyFlowStudio = { mount, defaultGraph, normalizeSections };
})(typeof window !== "undefined" ? window : globalThis);
