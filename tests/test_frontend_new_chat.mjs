import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";

function createElementStub(tagName = "div", id = "") {
  const listeners = new Map();
  const children = [];
  const attrs = new Map();
  const classSet = new Set();

  const el = {
    tagName: tagName.toUpperCase(),
    id,
    type: "",
    value: "",
    textContent: "",
    _innerHTML: "",
    disabled: false,
    tabIndex: 0,
    scrollTop: 0,
    scrollHeight: 40,
    clientHeight: 400,
    offsetWidth: 100,
    title: "",
    options: [],
    style: {},
    parentNode: null,
    attributes: attrs,
    classList: {
      add(...names) {
        for (const n of names) classSet.add(n);
      },
      remove(...names) {
        for (const n of names) classSet.delete(n);
      },
      toggle(name, force) {
        if (force === true) {
          classSet.add(name);
          return true;
        }
        if (force === false) {
          classSet.delete(name);
          return false;
        }
        if (classSet.has(name)) {
          classSet.delete(name);
          return false;
        }
        classSet.add(name);
        return true;
      },
      contains(name) {
        return classSet.has(name);
      },
    },
    get className() {
      return [...classSet].join(" ");
    },
    set className(val) {
      classSet.clear();
      for (const token of String(val || "").split(/\s+/).filter(Boolean)) {
        classSet.add(token);
      }
    },
    get children() {
      return children;
    },
    get innerHTML() {
      return this._innerHTML;
    },
    set innerHTML(val) {
      this._innerHTML = String(val ?? "");
      if (this._innerHTML === "") {
        children.length = 0;
      }
    },
    appendChild(child) {
      if (!child) return child;
      if (child.__isFragment) {
        for (const c of child.children) {
          c.parentNode = el;
          children.push(c);
        }
        child.children.length = 0;
        return child;
      }
      child.parentNode = el;
      children.push(child);
      return child;
    },
    remove() {
      if (el.parentNode && Array.isArray(el.parentNode.children)) {
        const idx = el.parentNode.children.indexOf(el);
        if (idx !== -1) el.parentNode.children.splice(idx, 1);
      }
      el.parentNode = null;
    },
    setAttribute(k, v) {
      attrs.set(String(k), String(v));
    },
    getAttribute(k) {
      return attrs.has(String(k)) ? attrs.get(String(k)) : null;
    },
    addEventListener(type, fn) {
      if (!listeners.has(type)) listeners.set(type, []);
      listeners.get(type).push(fn);
    },
    dispatchEvent(ev) {
      ev.target = ev.target || el;
      ev.currentTarget = el;
      if (typeof ev.preventDefault !== "function") {
        ev.defaultPrevented = false;
        ev.preventDefault = () => {
          ev.defaultPrevented = true;
        };
      }
      if (typeof ev.stopPropagation !== "function") {
        ev.stopPropagation = () => {};
      }
      const list = listeners.get(ev.type) || [];
      for (const fn of list) {
        fn(ev);
      }
      return !ev.defaultPrevented;
    },
    click() {
      return el.dispatchEvent({ type: "click" });
    },
    focus() {},
    contains(target) {
      if (target === el) return true;
      return children.some((c) => c.contains && c.contains(target));
    },
    querySelectorAll(selector) {
      const results = [];
      const walk = (node) => {
        for (const child of node.children || []) {
          if (matchesSelector(child, selector)) {
            results.push(child);
          }
          walk(child);
        }
      };
      walk(el);
      return results;
    },
    querySelector(selector) {
      return el.querySelectorAll(selector)[0] || null;
    },
  };
  return el;
}

function matchesSelector(node, selector) {
  if (!node) return false;
  if (selector.startsWith("#")) return node.id === selector.slice(1);
  if (selector.startsWith(".")) return node.classList.contains(selector.slice(1));
  return node.tagName === selector.toUpperCase();
}

function buildSandbox({
  clipboardImpl,
  mode = "mock",
  initialConversations = [],
  initialMessagesByConv = {},
} = {}) {
  const html = fs.readFileSync("frontend/index.html", "utf8");
  const tagMatches = [...html.matchAll(/<([a-zA-Z0-9-]+)\b([^>]*\bid="([^"]+)"[^>]*)>/g)];
  const elementsById = new Map();
  const rootBody = createElementStub("body", "__body");

  for (const m of tagMatches) {
    const htmlTag = m[1];
    const attrsStr = m[2];
    const id = m[3];
    const stub = createElementStub(htmlTag, id);
    const classMatch = attrsStr.match(/\bclass="([^"]*)"/);
    if (classMatch && classMatch[1]) {
      stub.className = classMatch[1];
    }
    for (const am of attrsStr.matchAll(/\b(aria-[a-z-]+)="([^"]*)"/g)) {
      stub.setAttribute(am[1], am[2]);
    }
    if (htmlTag === "input") {
      stub.files = [];
    }
    elementsById.set(id, stub);
    rootBody.appendChild(stub);
  }

  const chatCalls = [];
  const feedbackCalls = [];
  const fetchUrls = [];
  let holdChatResolve = null;
  let clipboardSelectionCount = 0;
  let feedbackShouldFail = false;
  let focusedEl = null;
  let serverConvs = initialConversations.map((c) => ({ ...c }));
  const serverMsgs = new Map(
    Object.entries(initialMessagesByConv).map(([k, v]) => [k, v.map((m) => ({ ...m }))])
  );
  for (const [k, s] of elementsById) {
    s.focus = () => {
      focusedEl = s;
    };
  }

  const docListeners = new Map();
  const documentStub = {
    documentElement: {
      attrs: new Map(),
      style: {},
      setAttribute(k, v) {
        this.attrs.set(k, v);
      },
      getAttribute(k) {
        return this.attrs.get(k) || null;
      },
    },
    body: rootBody,
    getElementById(id) {
      if (elementsById.has(id)) return elementsById.get(id);
      const findInTree = (node) => {
        for (const c of node.children || []) {
          if (c.id === id) return c;
          const found = findInTree(c);
          if (found) return found;
        }
        return null;
      };
      return findInTree(rootBody);
    },
    createElement(tag) {
      const node = createElementStub(tag);
      node.focus = () => {
        focusedEl = node;
      };
      return node;
    },
    createElementNS(_ns, tag) {
      return createElementStub(tag);
    },
    createDocumentFragment() {
      return {
        __isFragment: true,
        children: [],
        appendChild(child) {
          if (child && child.__isFragment) {
            this.children.push(...child.children);
            child.children.length = 0;
          } else if (child) {
            this.children.push(child);
          }
          return child;
        },
      };
    },
    createTextNode(text) {
      return createElementStub("#text");
    },
    createRange() {
      return {
        node: null,
        selectNodeContents(n) {
          this.node = n;
        },
      };
    },
    addEventListener(type, fn) {
      if (!docListeners.has(type)) docListeners.set(type, []);
      docListeners.get(type).push(fn);
    },
    dispatchEvent(ev) {
      ev.target = ev.target || rootBody;
      if (typeof ev.preventDefault !== "function") {
        ev.defaultPrevented = false;
        ev.preventDefault = () => {
          ev.defaultPrevented = true;
        };
      }
      if (typeof ev.stopPropagation !== "function") {
        ev.stopPropagation = () => {};
      }
      const list = docListeners.get(ev.type) || [];
      for (const fn of list) {
        fn(ev);
      }
      return !ev.defaultPrevented;
    },
  };

  const storageMap = new Map();
  const sessionMap = new Map();
  if (mode === "informatica") {
    sessionMap.set("maris_session_token:v1", "test.token.sig");
  }

  const windowStub = {
    innerWidth: 1280,
    localStorage: {
      get length() {
        return storageMap.size;
      },
      key: (i) => [...storageMap.keys()][i] ?? null,
      getItem: (k) => (storageMap.has(k) ? storageMap.get(k) : null),
      setItem: (k, v) => storageMap.set(k, String(v)),
      removeItem: (k) => storageMap.delete(k),
    },
    sessionStorage: {
      get length() {
        return sessionMap.size;
      },
      key: (i) => [...sessionMap.keys()][i] ?? null,
      getItem: (k) => (sessionMap.has(k) ? sessionMap.get(k) : null),
      setItem: (k, v) => sessionMap.set(k, String(v)),
      removeItem: (k) => sessionMap.delete(k),
    },
    getComputedStyle: () => ({
      lineHeight: "20px",
      paddingTop: "0px",
      paddingBottom: "0px",
    }),
    getSelection: () => ({
      removeAllRanges() {},
      addRange(r) {
        if (r && r.node) clipboardSelectionCount += 1;
      },
    }),
    addEventListener() {},
    matchMedia: () => ({ matches: false, addEventListener() {} }),
  };

  class FakeFileReader {
    constructor() {
      this.result = null;
      this.onload = null;
      this.onerror = null;
    }
    readAsDataURL(file) {
      const b64 = file && file._base64 ? file._base64 : Buffer.from("Hello MARIS", "utf8").toString("base64");
      const mime = (file && file.type) || "text/plain";
      this.result = `data:${mime};base64,${b64}`;
      if (typeof this.onload === "function") {
        this.onload();
      }
    }
  }

  async function fakeFetch(url, options = {}) {
    fetchUrls.push({ url, method: options.method || "GET" });
    if (url === "/api/health") {
      return { ok: true, status: 200, json: async () => ({ data_provider: mode }) };
    }
    if (url === "/api/session") {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          authenticated: mode === "informatica",
          role: mode === "informatica" ? "guest" : null,
          data_provider: mode,
        }),
      };
    }
    if (url === "/api/me") {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          customer_id: "1000000092615",
          first_name: "Dennis",
          last_name: "Woods",
          full_name: "Dennis Woods",
          personalization_consent: true,
          consent_configured: true,
          bookings: [],
        }),
      };
    }
    if (url === "/api/logout") {
      return { ok: true, status: 200, json: async () => ({ authenticated: false }) };
    }
    if (url === "/api/conversations" || url.startsWith("/api/conversations?q=")) {
      const qRaw = url.includes("?q=") ? decodeURIComponent(url.split("?q=")[1]) : "";
      const qLow = qRaw.trim().toLowerCase();
      const filtered = qLow
        ? serverConvs.filter(
            (c) =>
              c.title.toLowerCase().includes(qLow) ||
              (serverMsgs.get(c.id) || []).some((m) => String(m.text || "").toLowerCase().includes(qLow))
          )
        : serverConvs;
      return { ok: true, status: 200, json: async () => ({ conversations: filtered }) };
    }
    if (url.startsWith("/api/conversations/") && url !== "/api/conversations/title") {
      const cid = decodeURIComponent(url.slice("/api/conversations/".length));
      const method = (options.method || "GET").toUpperCase();
      const target = serverConvs.find((c) => c.id === cid);
      if (!target) {
        return { ok: false, status: 404, json: async () => ({ detail: "Conversation not found" }) };
      }
      if (method === "PATCH") {
        const patchBody = JSON.parse(options.body || "{}");
        target.title = String(patchBody.title || "").trim();
        return { ok: true, status: 200, json: async () => target };
      }
      if (method === "DELETE") {
        serverConvs = serverConvs.filter((c) => c.id !== cid);
        serverMsgs.delete(cid);
        return { ok: true, status: 200, json: async () => ({ deleted: true, id: cid }) };
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({
          ...target,
          messages: serverMsgs.get(cid) || [],
        }),
      };
    }
    if (url === "/api/feedback") {
      const fbBody = JSON.parse(options.body || "{}");
      feedbackCalls.push(fbBody);
      if (feedbackShouldFail) {
        return { ok: false, status: 500, json: async () => ({ detail: "Server unavailable" }) };
      }
      return { ok: true, status: 200, json: async () => fbBody };
    }
    if (url === "/api/guests") {
      return {
        ok: true,
        status: 200,
        json: async () => [
          {
            rcyc_id: "RCYC-1001",
            full_name: "Eleanor Vance",
            loyalty_tier: "Gold",
            past_voyages: 3,
            open_complaint_status: false,
            personalization_consent: true,
            profile_label: "Gold Member",
            guest_status: "returning",
          },
        ],
      };
    }
    if (url.startsWith("/api/guests/")) {
      const id = decodeURIComponent(url.split("/").pop());
      return {
        ok: true,
        status: 200,
        json: async () => ({
          status: "found",
          profile: {
            rcyc_id: id,
            first_name: id === "ANONYMOUS" ? "Visitor" : "Eleanor",
            last_name: id === "ANONYMOUS" ? "" : "Vance",
            loyalty_tier: "Gold",
            past_voyages: 3,
            previous_voyage_region: "Mediterranean",
            sailed_regions: ["Mediterranean"],
            preferred_suite: "Grand Suite",
            interest_focus: ["Culinary"],
            ancillary_purchase_preferences: ["Spa"],
            preferred_destinations: ["Northern Europe"],
            open_complaint_status: false,
            personalization_consent: id !== "ANONYMOUS",
            guest_status: id === "ANONYMOUS" ? "anonymous" : "returning",
          },
          bookings: [],
          escalation: false,
        }),
      };
    }
    if (url === "/api/conversations/title") {
      return { ok: true, status: 200, json: async () => ({ title: "Dining inquiry" }) };
    }
    if (url === "/api/chat") {
      const body = JSON.parse(options.body || "{}");
      chatCalls.push(body);
      if (body.message === "HOLD_REPLY") {
        return new Promise((resolve) => {
          holdChatResolve = () =>
            resolve({
              ok: true,
              status: 200,
              json: async () => ({
                reply: "Held reply",
                guest_profile: { rcyc_id: "RCYC-1001", first_name: "Eleanor", last_name: "Vance", loyalty_tier: "Gold", guest_status: "returning", personalization_consent: true },
                bookings: [],
                recommendations: [],
                referenced_voyages: [],
                suggested_replies: ["Best voyage for me"],
                escalation: { escalated: false },
                llm_provider_used: "rule_based",
              }),
            });
        });
      }
      const isGreet = /^\s*(hi|hello|hey|good morning)/i.test(body.message) && !body.attachment;
      const nowIso = new Date().toISOString();
      const convId = body.conversation_id || `conv_${chatCalls.length}`;
      const replyText = isGreet
        ? "Hello, Eleanor. What would you like to explore today?"
        : `Reply for **${body.message}**`;
      const userMsgId = `msg_u_${chatCalls.length}`;
      const asstMsgId = `msg_a_${chatCalls.length}`;
      if (mode === "informatica") {
        if (!serverConvs.some((c) => c.id === convId)) {
          serverConvs.unshift({
            id: convId,
            title: body.message.split(/\s+/).slice(0, 6).join(" "),
            created_at: nowIso,
            updated_at: nowIso,
          });
        }
        const arr = serverMsgs.get(convId) || [];
        arr.push({ id: userMsgId, role: "user", text: body.message, created_at: nowIso, vote: null });
        arr.push({ id: asstMsgId, role: "assistant", text: replyText, created_at: nowIso, vote: null });
        serverMsgs.set(convId, arr);
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({
          reply: replyText,
          guest_profile: { rcyc_id: "RCYC-1001", first_name: "Eleanor", last_name: "Vance", loyalty_tier: "Gold", guest_status: "returning", personalization_consent: true },
          bookings: [],
          recommendations: [],
          referenced_voyages: [],
          suggested_replies: ["Best voyage for me", "My bookings"],
          escalation: { escalated: false },
          llm_provider_used: "rule_based",
          ...(mode === "informatica"
            ? {
                conversation_id: convId,
                conversation_title: body.message.split(/\s+/).slice(0, 6).join(" "),
                user_message_id: userMsgId,
                assistant_message_id: asstMsgId,
                user_created_at: nowIso,
                assistant_created_at: nowIso,
              }
            : {}),
        }),
      };
    }
    return { ok: true, status: 200, json: async () => ({}) };
  }

  const context = {
    window: windowStub,
    document: documentStub,
    navigator: { clipboard: clipboardImpl },
    FileReader: FakeFileReader,
    fetch: fakeFetch,
    Headers,
    URLSearchParams,
    console,
    setTimeout,
    clearTimeout,
    Map,
    Set,
    Date,
    Math,
    Promise,
  };
  const code = fs.readFileSync("frontend/app.js", "utf8");
  vm.runInNewContext(code, context, { filename: "frontend/app.js" });

  return {
    elementsById,
    documentStub,
    windowStub,
    storageMap,
    sessionMap,
    chatCalls,
    feedbackCalls,
    fetchUrls,
    setFeedbackShouldFail: (v) => {
      feedbackShouldFail = Boolean(v);
    },
    getFocusedEl: () => focusedEl,
    releaseHold: () => holdChatResolve && holdChatResolve(),
    getSelectionCount: () => clipboardSelectionCount,
  };
}

async function flush() {
  for (let i = 0; i < 8; i++) {
    await new Promise((r) => setTimeout(r, 15));
  }
}

async function run() {
  // 1. Welcome section, sidebar profile & collapse/open persistence, theme toggle, cards, greeting chips, Enter/Shift+Enter/IME/busy, Copy, Attachments
  let copiedText = "";
  const sb1 = buildSandbox({
    clipboardImpl: {
      writeText: async (text) => {
        copiedText = text;
      },
    },
  });
  await flush();

  const welcomeSection = sb1.documentStub.getElementById("welcomeSection");
  assert.ok(welcomeSection, "Empty chat should render #welcomeSection");
  assert.equal(welcomeSection.querySelector("img"), null, "Welcome section should not render logo image");
  const heading = welcomeSection.querySelector(".welcome-heading");
  assert.equal(heading.textContent, "How can I help you today, Eleanor?");
  const cards = welcomeSection.querySelectorAll(".welcome-action-card");
  assert.equal(cards.length, 4, "Should render 4 welcome cards");
  assert.deepEqual(
    cards.map((c) => c.getAttribute("data-focus")),
    ["voyages", "culinary", "wellness", "adventure_cultural"]
  );
  const quickPrompts = sb1.elementsById.get("quickPrompts");
  assert.ok(quickPrompts.classList.contains("is-chips-hidden"), "Starting chips should be hidden while welcome cards are shown");

  // Sidebar profile row shows initials & first name
  assert.equal(sb1.elementsById.get("sidebarProfileAvatar").textContent, "EV");
  assert.equal(sb1.elementsById.get("sidebarProfileName").textContent, "Eleanor");

  // Sidebar collapse & open persists in sessionStorage
  const workspaceMain = sb1.elementsById.get("workspaceMain");
  const sidebarToggleBtn = sb1.elementsById.get("sidebarToggleBtn");
  const openSidebarBtn = sb1.elementsById.get("openSidebarBtn");
  assert.equal(workspaceMain.classList.contains("is-sidebar-collapsed"), false);
  assert.equal(openSidebarBtn.classList.contains("hidden"), true);
  sidebarToggleBtn.click();
  assert.equal(workspaceMain.classList.contains("is-sidebar-collapsed"), true);
  assert.equal(openSidebarBtn.classList.contains("hidden"), false);
  assert.equal(sb1.sessionMap.get("maris_history_sidebar_open:v1:desktop"), "false");
  openSidebarBtn.click();
  assert.equal(workspaceMain.classList.contains("is-sidebar-collapsed"), false);
  assert.equal(openSidebarBtn.classList.contains("hidden"), true);
  assert.equal(sb1.sessionMap.get("maris_history_sidebar_open:v1:desktop"), "true");

  // Theme toggle is only in the top-right header (removed from sidebar popover) and switches light <-> dark
  assert.equal(sb1.elementsById.get("themeToggleBtn"), undefined);
  const topbarThemeToggleBtn = sb1.elementsById.get("topbarThemeToggleBtn");
  const topbarThemeIconMoon = sb1.elementsById.get("topbarThemeIconMoon");
  const topbarThemeIconSun = sb1.elementsById.get("topbarThemeIconSun");
  assert.equal(topbarThemeToggleBtn.getAttribute("aria-pressed"), "false");
  assert.equal(topbarThemeIconMoon.classList.contains("hidden"), false);
  assert.equal(topbarThemeIconSun.classList.contains("hidden"), true);
  topbarThemeToggleBtn.click();
  assert.equal(sb1.documentStub.documentElement.getAttribute("data-theme"), "dark");
  assert.equal(topbarThemeToggleBtn.getAttribute("aria-pressed"), "true");
  assert.equal(topbarThemeIconMoon.classList.contains("hidden"), true);
  assert.equal(topbarThemeIconSun.classList.contains("hidden"), false);
  topbarThemeToggleBtn.click();
  assert.equal(sb1.documentStub.documentElement.getAttribute("data-theme"), "light");
  assert.equal(topbarThemeToggleBtn.getAttribute("aria-pressed"), "false");
  assert.equal(topbarThemeIconMoon.classList.contains("hidden"), false);
  assert.equal(topbarThemeIconSun.classList.contains("hidden"), true);

  // Click card 2 ("Dining & culinary" -> focus: "culinary")
  cards[1].click();
  await flush();
  assert.equal(sb1.documentStub.getElementById("welcomeSection"), null, "Welcome section must disappear after sending");
  assert.equal(sb1.chatCalls[0].message, "Dining & culinary");
  assert.equal(sb1.chatCalls[0].focus, "culinary");

  // Copy button exists only on assistant messages, copies plain text (no markdown **)
  const chatMessages = sb1.elementsById.get("chatMessages");
  const userRows = chatMessages.querySelectorAll(".user");
  const assistantRows = chatMessages.querySelectorAll(".assistant");
  assert.equal(userRows.length, 1);
  assert.equal(assistantRows.length, 1);
  assert.equal(userRows[0].querySelector(".copy-reply-btn"), null, "No copy button on user messages");
  const copyBtn = assistantRows[0].querySelector(".copy-reply-btn");
  assert.ok(copyBtn, "Copy button must exist on MARIS replies");
  assert.equal(copyBtn.getAttribute("aria-label"), "Copy reply");
  copyBtn.click();
  await flush();
  assert.equal(copiedText, "Reply for Dining & culinary");
  const copyLabel = copyBtn.querySelector(".copy-reply-label");
  assert.equal(copyLabel.textContent, "Copied");

  // Multi-line composer checks
  const input = sb1.elementsById.get("messageInput");

  // Whitespace-only + Enter should preventDefault and NOT send
  const prevCalls = sb1.chatCalls.length;
  input.value = "   \n  ";
  const wsEv = { type: "keydown", key: "Enter", shiftKey: false, isComposing: false, keyCode: 13 };
  input.dispatchEvent(wsEv);
  await flush();
  assert.equal(wsEv.defaultPrevented, true);
  assert.equal(sb1.chatCalls.length, prevCalls, "Whitespace-only must not send");

  // Shift+Enter should NOT preventDefault and must NOT send
  input.value = "Line 1";
  const shiftEv = { type: "keydown", key: "Enter", shiftKey: true, isComposing: false, keyCode: 13 };
  input.dispatchEvent(shiftEv);
  await flush();
  assert.equal(shiftEv.defaultPrevented, false);
  assert.equal(sb1.chatCalls.length, prevCalls, "Shift+Enter must not send");

  // IME composition active must NOT send or preventDefault
  const imeEv = { type: "keydown", key: "Enter", shiftKey: false, isComposing: true, keyCode: 229 };
  input.dispatchEvent(imeEv);
  await flush();
  assert.equal(imeEv.defaultPrevented, false);
  assert.equal(sb1.chatCalls.length, prevCalls, "IME composing must not send");

  // Enter sends trimmed greeting and reveals starting chips immediately
  input.value = "hi";
  const enterEv = { type: "keydown", key: "Enter", shiftKey: false, isComposing: false, keyCode: 13 };
  input.dispatchEvent(enterEv);
  await flush();
  assert.equal(enterEv.defaultPrevented, true);
  assert.equal(sb1.chatCalls.length, prevCalls + 1);
  assert.equal(sb1.chatCalls[prevCalls].message, "hi");
  assert.equal(input.value, "");
  assert.equal(quickPrompts.classList.contains("is-chips-hidden"), false, "Starting chips should show after greeting reply");

  // Attachment validation & send check (wrong type, > 10 MB, valid .txt, never persisted in localStorage)
  const fileInput = sb1.elementsById.get("fileAttachInput");
  const attachError = sb1.elementsById.get("attachmentError");
  const attachChipWrap = sb1.elementsById.get("attachmentChipWrap");

  fileInput.files = [{ name: "bad.exe", type: "application/x-msdownload", size: 512 }];
  fileInput.dispatchEvent({ type: "change" });
  assert.equal(attachError.classList.contains("hidden"), false, "Unsupported file type must show error");
  assert.ok(attachError.textContent.toLowerCase().includes("unsupported"));

  fileInput.files = [{ name: "huge.pdf", type: "application/pdf", size: 11 * 1024 * 1024 }];
  fileInput.dispatchEvent({ type: "change" });
  assert.equal(attachError.classList.contains("hidden"), false, "Over 10MB file must show error");
  assert.ok(attachError.textContent.toLowerCase().includes("10 mb"));

  const sampleB64 = Buffer.from("Ritz-Carlton packing checklist", "utf8").toString("base64");
  fileInput.files = [{ name: "notes.txt", type: "text/plain", size: 30, _base64: sampleB64 }];
  fileInput.dispatchEvent({ type: "change" });
  assert.equal(attachError.classList.contains("hidden"), true);
  assert.equal(attachChipWrap.classList.contains("hidden"), false);
  assert.equal(sb1.elementsById.get("attachmentFileName").textContent, "notes.txt");

  input.value = "Summarize this note";
  input.dispatchEvent({ type: "keydown", key: "Enter", shiftKey: false, isComposing: false, keyCode: 13 });
  await flush();
  const lastChatReq = sb1.chatCalls[sb1.chatCalls.length - 1];
  assert.deepEqual(lastChatReq.attachment, {
    name: "notes.txt",
    mime_type: "text/plain",
    data_base64: sampleB64,
  });
  assert.equal(attachChipWrap.classList.contains("hidden"), true, "Chip clears after send");
  const storedJson = [...sb1.storageMap.values()].join("\n");
  assert.equal(storedJson.includes(sampleB64), false, "Attachment base64 must never be stored in localStorage");
  assert.equal(storedJson.includes("notes.txt"), true, "Filename badge may persist in conversation UI message");

  // Busy state blocks Enter send
  input.value = "HOLD_REPLY";
  input.dispatchEvent({ type: "keydown", key: "Enter", shiftKey: false, isComposing: false, keyCode: 13 });
  await new Promise((r) => setTimeout(r, 10));
  const duringHoldCalls = sb1.chatCalls.length;
  input.value = "Should be ignored while busy";
  input.dispatchEvent({ type: "keydown", key: "Enter", shiftKey: false, isComposing: false, keyCode: 13 });
  assert.equal(sb1.chatCalls.length, duringHoldCalls, "Enter must not send while MARIS is replying");
  sb1.releaseHold();
  await flush();

  // 2. Test clipboard failure fallback -> selects text and shows "Press Ctrl+C" without throwing
  const sb2 = buildSandbox({
    clipboardImpl: {
      writeText: async () => {
        throw new Error("Clipboard blocked");
      },
    },
  });
  await flush();
  const input2 = sb2.elementsById.get("messageInput");
  input2.value = "Test fallback copy";
  input2.dispatchEvent({ type: "keydown", key: "Enter", shiftKey: false, isComposing: false, keyCode: 13 });
  await flush();
  const copyBtn2 = sb2.elementsById.get("chatMessages").querySelector(".copy-reply-btn");
  assert.ok(copyBtn2);
  copyBtn2.click();
  await flush();
  assert.equal(sb2.getSelectionCount(), 1, "Fallback should select reply text");
  assert.equal(copyBtn2.querySelector(".copy-reply-label").textContent, "Press Ctrl+C");

  // 3. Message timestamps under bubbles, smart auto-scroll, & Profile menu popover/Esc/outside-click
  const uTime1 = userRows[0].querySelector(".user-msg-time");
  const aTime1 = assistantRows[0].querySelector(".assistant-msg-time");
  assert.ok(uTime1 && /^\d{2}:\d{2}$/.test(uTime1.textContent), "Guest message renders HH:MM timestamp underneath");
  assert.ok(aTime1 && /^\d{2}:\d{2}$/.test(aTime1.textContent), "MARIS reply renders HH:MM timestamp in footer");

  // Smart auto-scroll: scrolled up preserves scrollTop on incoming reply; new user message forces scroll to bottom
  chatMessages.scrollHeight = 1200;
  chatMessages.clientHeight = 400;
  chatMessages.scrollTop = 100;
  chatMessages.dispatchEvent({ type: "scroll" });
  input.value = "HOLD_REPLY";
  // Sending user message forces scroll to bottom first
  input.dispatchEvent({ type: "keydown", key: "Enter", shiftKey: false, isComposing: false, keyCode: 13 });
  assert.equal(chatMessages.scrollTop, 1200, "Sending user message forces scroll to bottom");
  // Now guest scrolls up while MARIS is typing
  chatMessages.scrollHeight = 1400;
  chatMessages.scrollTop = 250;
  chatMessages.dispatchEvent({ type: "scroll" });
  sb1.releaseHold();
  await flush();
  assert.equal(chatMessages.scrollTop, 250, "Incoming MARIS reply does not snap scroll if guest scrolled up");

  // Profile menu: default hidden, aria-expanded, Esc restores focus, outside click closes
  const accountMenuBtn = sb1.elementsById.get("accountMenuBtn");
  const accountPopover = sb1.elementsById.get("accountPopover");
  assert.equal(accountPopover.classList.contains("hidden"), true);
  assert.equal(accountMenuBtn.getAttribute("aria-expanded"), "false");
  accountMenuBtn.click();
  assert.equal(accountPopover.classList.contains("hidden"), false);
  assert.equal(accountMenuBtn.getAttribute("aria-expanded"), "true");
  sb1.documentStub.dispatchEvent({ type: "keydown", key: "Escape" });
  assert.equal(accountPopover.classList.contains("hidden"), true);
  assert.equal(accountMenuBtn.getAttribute("aria-expanded"), "false");
  assert.equal(sb1.getFocusedEl(), accountMenuBtn, "Esc restores focus to profile menu trigger");
  accountMenuBtn.click();
  assert.equal(accountPopover.classList.contains("hidden"), false);
  sb1.documentStub.dispatchEvent({ type: "click", target: sb1.documentStub.body });
  assert.equal(accountPopover.classList.contains("hidden"), true);

  // 4. Signed-in Informatica mode: date groups, previous-day timestamp, Rename/Delete/Search, Feedback error vs upsert, Sign-out cleanup
  const nowMs = Date.now();
  const isoToday = new Date(nowMs - 60 * 1000).toISOString();
  const isoYesterday = new Date(nowMs - 24 * 60 * 60 * 1000).toISOString();
  const isoPrev7 = new Date(nowMs - 4 * 24 * 60 * 60 * 1000).toISOString();
  const isoOlder = new Date(nowMs - 14 * 24 * 60 * 60 * 1000).toISOString();

  const sbInfa = buildSandbox({
    mode: "informatica",
    clipboardImpl: { writeText: async () => {} },
    initialConversations: [
      { id: "c_today", title: "Today Med Inquiry", created_at: isoToday, updated_at: isoToday },
      { id: "c_yest", title: "Yesterday Dining", created_at: isoYesterday, updated_at: isoYesterday },
      { id: "c_week", title: "Week Ilma Plan", created_at: isoPrev7, updated_at: isoPrev7 },
      { id: "c_old", title: "Older Luminara Q", created_at: isoOlder, updated_at: isoOlder },
    ],
    initialMessagesByConv: {
      c_yest: [
        { id: "m_u_old", role: "user", text: "Show dining options", created_at: isoYesterday, vote: null },
        { id: "m_a_old", role: "assistant", text: "Evrima offers **The Dining Room**.", created_at: isoYesterday, vote: null },
      ],
    },
  });
  await flush();

  // Group labels in sidebar
  const histList = sbInfa.elementsById.get("historyList");
  const groupLabels = histList.querySelectorAll(".history-group-label").map((g) => g.textContent);
  assert.deepEqual(groupLabels, ["Today", "Yesterday", "Previous 7 Days", "Older"]);

  // Open Yesterday conversation and verify date included in non-today timestamp
  const yestSelectBtns = histList.querySelectorAll(".history-item-select");
  yestSelectBtns[1].click();
  await flush();
  const loadedAsst = sbInfa.elementsById.get("chatMessages").querySelectorAll(".assistant")[0];
  const loadedTimeText = loadedAsst.querySelector(".assistant-msg-time").textContent;
  assert.ok(/^[A-Z][a-z]{2}\s+\d{1,2},.*\d{2}:\d{2}$/.test(loadedTimeText), `Expected date + HH:MM for yesterday, got ${loadedTimeText}`);

  // Feedback error keeps unselected state & shows inline error; success updates vote up -> down
  const upBtn = loadedAsst.querySelector(".feedback-up-btn");
  const downBtn = loadedAsst.querySelector(".feedback-down-btn");
  const fbErrEl = loadedAsst.querySelector(".feedback-error");
  assert.ok(upBtn && downBtn && fbErrEl);
  sbInfa.setFeedbackShouldFail(true);
  upBtn.click();
  await flush();
  assert.equal(upBtn.classList.contains("is-selected"), false, "Must not mark selected when server save fails");
  assert.equal(fbErrEl.classList.contains("hidden"), false, "Must show inline feedback error");

  sbInfa.setFeedbackShouldFail(false);
  upBtn.click();
  await flush();
  assert.equal(upBtn.classList.contains("is-selected"), true);
  assert.equal(fbErrEl.classList.contains("hidden"), true);
  downBtn.click();
  await flush();
  assert.equal(upBtn.classList.contains("is-selected"), false);
  assert.equal(downBtn.classList.contains("is-selected"), true);
  assert.equal(sbInfa.feedbackCalls.length, 3);

  // "..." menu -> Rename inline (Enter) & Delete confirm ("Delete this conversation? This cannot be undone.")
  const menuBtns = histList.querySelectorAll(".history-row-menu-btn");
  menuBtns[0].click();
  const rowActions = histList.querySelectorAll(".history-row-action");
  assert.deepEqual(rowActions.map((a) => a.textContent), ["Rename", "Delete"]);
  rowActions[0].click();
  const renameInput = histList.querySelector(".history-rename-input");
  assert.ok(renameInput);
  renameInput.value = "Renamed Med Cruise";
  renameInput.dispatchEvent({ type: "keydown", key: "Enter" });
  await flush();
  assert.equal(histList.querySelectorAll(".history-item-title")[0].textContent, "Renamed Med Cruise");

  // Open Delete confirm and check exact prompt
  histList.querySelectorAll(".history-row-menu-btn")[0].click();
  histList.querySelectorAll(".history-row-action")[1].click();
  const confirmBar = histList.querySelector(".history-confirm-bar");
  assert.ok(confirmBar);
  assert.equal(confirmBar.querySelector("span").textContent, "Delete this conversation? This cannot be undone.");
  confirmBar.querySelector(".history-confirm-yes").click();
  await flush();
  assert.equal(histList.querySelectorAll(".history-item").length, 3);

  // Debounced search (250ms) triggers /api/conversations?q=...
  const searchInput = sbInfa.elementsById.get("historySearchInput");
  searchInput.value = "nomatchxyz";
  searchInput.dispatchEvent({ type: "input" });
  await new Promise((r) => setTimeout(r, 320));
  await flush();
  assert.ok(sbInfa.fetchUrls.some((f) => f.url === "/api/conversations?q=nomatchxyz"));
  assert.equal(histList.querySelector(".history-empty").textContent, "No matching conversations.");

  // Sign out wipes conversation storage keys & UI state
  sbInfa.storageMap.set("maris_conversations:v1:1000000092615", "stale");
  sbInfa.storageMap.set("maris_active_conv:v1:1000000092615", "c_today");
  sbInfa.elementsById.get("popoverLogoutBtn").click();
  await flush();
  assert.equal(sbInfa.sessionMap.has("maris_session_token:v1"), false);
  assert.equal(sbInfa.storageMap.has("maris_conversations:v1:1000000092615"), false);
  assert.equal(sbInfa.storageMap.has("maris_active_conv:v1:1000000092615"), false);
  assert.equal(sbInfa.elementsById.get("historyList").children.length, 0);

  console.log("PASS: Frontend welcome cards, timestamps, smart scroll, profile popover, grouped history, rename/delete/search, feedback, sign-out cleanup & copy fallback tests");
}

run().catch((err) => {
  console.error(err);
  process.exit(1);
});
