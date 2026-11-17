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

function buildSandbox({ clipboardImpl }) {
  const html = fs.readFileSync("frontend/index.html", "utf8");
  const ids = [...html.matchAll(/id="([^"]+)"/g)].map((m) => m[1]);
  const elementsById = new Map();
  const rootBody = createElementStub("body", "__body");

  for (const id of ids) {
    const tag =
      id === "messageInput"
        ? "textarea"
        : id.includes("Form")
        ? "form"
        : id === "fileAttachInput"
        ? "input"
        : "div";
    const stub = createElementStub(tag, id);
    if (tag === "input") {
      stub.files = [];
    }
    elementsById.set(id, stub);
    rootBody.appendChild(stub);
  }

  const chatCalls = [];
  let holdChatResolve = null;
  let clipboardSelectionCount = 0;

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
      return createElementStub(tag);
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
  };

  const storageMap = new Map();
  const sessionMap = new Map();

  const windowStub = {
    innerWidth: 1280,
    localStorage: {
      getItem: (k) => (storageMap.has(k) ? storageMap.get(k) : null),
      setItem: (k, v) => storageMap.set(k, String(v)),
      removeItem: (k) => storageMap.delete(k),
    },
    sessionStorage: {
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
    if (url === "/api/health") {
      return { ok: true, status: 200, json: async () => ({ data_provider: "mock" }) };
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
      return {
        ok: true,
        status: 200,
        json: async () => ({
          reply: isGreet
            ? "Hello, Eleanor. What would you like to explore today?"
            : `Reply for **${body.message}**`,
          guest_profile: { rcyc_id: "RCYC-1001", first_name: "Eleanor", last_name: "Vance", loyalty_tier: "Gold", guest_status: "returning", personalization_consent: true },
          bookings: [],
          recommendations: [],
          referenced_voyages: [],
          suggested_replies: ["Best voyage for me", "My bookings"],
          escalation: { escalated: false },
          llm_provider_used: "rule_based",
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

  // Theme toggle inside account popover switches light <-> dark
  const themeToggleBtn = sb1.elementsById.get("themeToggleBtn");
  const themeToggleLabel = sb1.elementsById.get("themeToggleLabel");
  assert.equal(themeToggleLabel.textContent, "Dark mode");
  themeToggleBtn.click();
  assert.equal(sb1.documentStub.documentElement.getAttribute("data-theme"), "dark");
  assert.equal(themeToggleLabel.textContent, "Light mode");
  themeToggleBtn.click();
  assert.equal(sb1.documentStub.documentElement.getAttribute("data-theme"), "light");

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

  console.log("PASS: Frontend welcome cards, sidebar toggle/sessionStorage, popover theme, Enter/Shift+Enter/IME/busy composer, attachments, greeting chips, and copy fallback tests");
}

run().catch((err) => {
  console.error(err);
  process.exit(1);
});
