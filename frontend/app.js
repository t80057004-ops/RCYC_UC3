/**
 * MARIS – RCYC Guest Concierge Frontend Controller
 */

const ANONYMOUS_FALLBACK_PROFILE = {
  rcyc_id: "ANONYMOUS",
  first_name: "Visitor",
  last_name: "",
  loyalty_tier: "None",
  past_voyages: 0,
  previous_voyage_region: "None",
  sailed_regions: [],
  preferred_suite: "Not specified",
  interest_focus: [],
  ancillary_purchase_preferences: [],
  preferred_destinations: [],
  open_complaint_status: false,
  personalization_consent: false,
  profile_label: "Anonymous Visitor",
  guest_status: "anonymous",
};

const CHAT_STORAGE_PREFIX = "maris_chat_session:v1";
const CONVERSATIONS_STORAGE_PREFIX = "maris_conversations:v1";
const ACTIVE_CONVERSATION_PREFIX = "maris_active_conv:v1";
const SIDEBAR_OPEN_DESKTOP_KEY = "maris_history_sidebar_open:v1:desktop";
const SIDEBAR_OPEN_MOBILE_KEY = "maris_history_sidebar_open:v1:mobile";
const ACTIVE_MOCK_GUEST_KEY = "maris_active_mock_guest:v1";
const SESSION_TOKEN_KEY = "maris_session_token:v1";
const MAX_CONVERSATIONS_PER_CUSTOMER = 30;
const MAX_MESSAGES_PER_CONVERSATION = 60;
const MOBILE_BREAKPOINT_PX = 760;

const memoryConversationsStore = new Map();

const state = {
  mode: "mock",
  me: null,
  rcycId: "ANONYMOUS",
  sampleIds: new Set(["ANONYMOUS"]),
  guestListAvailable: true,
  profile: ANONYMOUS_FALLBACK_PROFILE,
  bookings: [],
  conversations: [],
  activeConversationId: null,
  pendingDeleteConversationId: null,
  sidebarOpen: true,
  history: [],
  uiMessages: [],
  busy: false,
  voyagesLoaded: false,
};

const el = {
  infaLoginView: document.getElementById("infaLoginView"),
  infaLoginForm: document.getElementById("infaLoginForm"),
  loginCustomerId: document.getElementById("loginCustomerId"),
  loginPassword: document.getElementById("loginPassword"),
  togglePasswordBtn: document.getElementById("togglePasswordBtn"),
  loginError: document.getElementById("loginError"),
  loginSubmitBtn: document.getElementById("loginSubmitBtn"),
  workspaceMain: document.getElementById("workspaceMain"),
  sidebarToggleBtn: document.getElementById("sidebarToggleBtn"),
  historyDrawerBackdrop: document.getElementById("historyDrawerBackdrop"),
  historySidebar: document.getElementById("historySidebar"),
  closeHistoryDrawerBtn: document.getElementById("closeHistoryDrawerBtn"),
  newConversationBtn: document.getElementById("newConversationBtn"),
  historyList: document.getElementById("historyList"),
  chatIdentityStrip: document.getElementById("chatIdentityStrip"),
  guestPickerSection: document.getElementById("guestPickerSection"),
  guestPickerDivider: document.getElementById("guestPickerDivider"),
  demoFooter: document.getElementById("demoFooter"),
  guestSelect: document.getElementById("guestSelect"),
  inlineGuestSelect: document.getElementById("inlineGuestSelect"),
  inlineLookupForm: document.getElementById("inlineLookupForm"),
  inlineRcycInput: document.getElementById("inlineRcycInput"),
  idLookupFeedback: document.getElementById("idLookupFeedback"),
  headerGreeting: document.getElementById("headerGreeting"),
  accountMenuBtn: document.getElementById("accountMenuBtn"),
  accountPopover: document.getElementById("accountPopover"),
  popoverMyProfileBtn: document.getElementById("popoverMyProfileBtn"),
  popoverSwitchAnonBtn: document.getElementById("popoverSwitchAnonBtn"),
  popoverLogoutBtn: document.getElementById("popoverLogoutBtn"),
  conciergeStatusIndicator: document.getElementById("conciergeStatusIndicator"),
  conciergeStatusText: document.getElementById("conciergeStatusText"),
  demoInsightsToggleBtn: document.getElementById("demoInsightsToggleBtn"),
  demoInsightsDrawer: document.getElementById("demoInsightsDrawer"),
  closeDemoInsightsBtn: document.getElementById("closeDemoInsightsBtn"),
  insightEngineText: document.getElementById("insightEngineText"),
  usedFieldsList: document.getElementById("usedFieldsList"),
  insightScoreBreakdown: document.getElementById("insightScoreBreakdown"),
  escalationBanner: document.getElementById("escalationBanner"),
  escalationReasonText: document.getElementById("escalationReasonText"),
  escalationNoteText: document.getElementById("escalationNoteText"),
  escalationPacketPre: document.getElementById("escalationPacketPre"),
  toggleContextPacketBtn: document.getElementById("toggleContextPacketBtn"),
  chatMessages: document.getElementById("chatMessages"),
  typingIndicator: document.getElementById("typingIndicator"),
  chatForm: document.getElementById("chatForm"),
  messageInput: document.getElementById("messageInput"),
  sendBtn: document.getElementById("sendBtn"),
  mobileDetailsToggle: document.getElementById("mobileDetailsToggle"),
  mobileDetailsChevron: document.getElementById("mobileDetailsChevron"),
  sidebarPanel: document.getElementById("guest-profile-panel"),
  profileKicker: document.getElementById("profileKicker"),
  vipBadge: document.getElementById("vipBadge"),
  profileName: document.getElementById("profileName"),
  profileStatusSubtitle: document.getElementById("profileStatusSubtitle"),
  consentOffNotice: document.getElementById("consentOffNotice"),
  demoConsentNotice: document.getElementById("demoConsentNotice"),
  profileIdLabel: document.getElementById("profileIdLabel"),
  profileRcycId: document.getElementById("profileRcycId"),
  rowInfaEmail: document.getElementById("rowInfaEmail"),
  attrInfaEmail: document.getElementById("attrInfaEmail"),
  rowInfaPhone: document.getElementById("rowInfaPhone"),
  attrInfaPhone: document.getElementById("attrInfaPhone"),
  rowInfaLoyalty: document.getElementById("rowInfaLoyalty"),
  attrInfaLoyalty: document.getElementById("attrInfaLoyalty"),
  rowConsent: document.getElementById("rowConsent"),
  attrConsent: document.getElementById("attrConsent"),
  rowPreferredRegions: document.getElementById("rowPreferredRegions"),
  attrPreferredRegions: document.getElementById("attrPreferredRegions"),
  rowSuiteAncillary: document.getElementById("rowSuiteAncillary"),
  attrSuiteAncillary: document.getElementById("attrSuiteAncillary"),
  specialNotesRow: document.getElementById("specialNotesRow"),
  attrSpecialNotes: document.getElementById("attrSpecialNotes"),
  complaintRow: document.getElementById("complaintRow"),
  attrComplaint: document.getElementById("attrComplaint"),
  mockBookingsTable: document.getElementById("mockBookingsTable"),
  infaBookingsList: document.getElementById("infaBookingsList"),
  metricVoyages: document.getElementById("metricVoyages"),
  attrPrevRegion: document.getElementById("attrPrevRegion"),
  metricBooking: document.getElementById("metricBooking"),
  profileEscalationBadge: document.getElementById("profileEscalationBadge"),
  profileEscalationDetail: document.getElementById("profileEscalationDetail"),
  yourDetailsModal: document.getElementById("yourDetailsModal"),
  closeDetailsModalBtn: document.getElementById("closeDetailsModalBtn"),
  yourDetailsModalBody: document.getElementById("yourDetailsModalBody"),
  popoverDataPanelBtn: document.getElementById("popoverDataPanelBtn"),
  dataDrawer: document.getElementById("dataDrawer"),
  dataDrawerBackdrop: document.getElementById("dataDrawerBackdrop"),
  closeDataDrawerBtn: document.getElementById("closeDataDrawerBtn"),
  catalogTriggerBtn: document.getElementById("catalogTriggerBtn"),
  closeCatalogBtn: document.getElementById("closeCatalogBtn"),
  catalogModal: document.getElementById("catalogModal"),
  catalogGrid: document.getElementById("catalogGrid"),
};

function currentTimeStr() {
  return new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function safeStorageGet(key) {
  try {
    if (typeof window !== "undefined" && window.localStorage) {
      const val = window.localStorage.getItem(key);
      if (val !== null) return val;
    }
  } catch (err) {
    // Fall back to memory store
  }
  return memoryConversationsStore.has(key) ? memoryConversationsStore.get(key) : null;
}

function safeStorageSet(key, value) {
  try {
    if (typeof window !== "undefined" && window.localStorage) {
      window.localStorage.setItem(key, value);
      memoryConversationsStore.delete(key);
      return true;
    }
  } catch (err) {
    // Fall back to memory store when localStorage is unavailable or full
  }
  memoryConversationsStore.set(key, value);
  return false;
}

function safeStorageRemove(key) {
  memoryConversationsStore.delete(key);
  try {
    if (typeof window !== "undefined" && window.localStorage) {
      window.localStorage.removeItem(key);
    }
  } catch (err) {
    // Ignore storage access errors
  }
}

function getSessionToken() {
  try {
    if (typeof window === "undefined" || !window.sessionStorage) return "";
    return window.sessionStorage.getItem(SESSION_TOKEN_KEY) || "";
  } catch (err) {
    return "";
  }
}

function setSessionToken(token) {
  try {
    if (typeof window === "undefined" || !window.sessionStorage) return;
    if (token) {
      window.sessionStorage.setItem(SESSION_TOKEN_KEY, token);
    } else {
      window.sessionStorage.removeItem(SESSION_TOKEN_KEY);
    }
  } catch (err) {
    // Ignore sessionStorage errors
  }
}

function clearSessionToken() {
  try {
    if (typeof window === "undefined" || !window.sessionStorage) return;
    window.sessionStorage.removeItem(SESSION_TOKEN_KEY);
  } catch (err) {
    // Ignore sessionStorage errors
  }
}

function apiFetch(url, options = {}) {
  const headers = new Headers(options.headers || {});
  const token = getSessionToken();
  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  return fetch(url, {
    ...options,
    headers,
    credentials: options.credentials || "same-origin",
  });
}

function getLegacyChatStorageKey(sessionIdOverride = null) {
  const rawId = sessionIdOverride ?? state.rcycId ?? (state.mode === "informatica" ? "" : "ANONYMOUS");
  const normalizedId = String(rawId || "").trim().toUpperCase();
  if (!normalizedId) return null;
  return `${CHAT_STORAGE_PREFIX}:${state.mode}:${normalizedId}`;
}

function getConversationsStorageKey(sessionIdOverride = null) {
  const rawId = sessionIdOverride ?? state.rcycId ?? (state.mode === "informatica" ? "" : "ANONYMOUS");
  const normalizedId = String(rawId || "").trim().toUpperCase();
  if (!normalizedId) return null;
  return `${CONVERSATIONS_STORAGE_PREFIX}:${state.mode}:${normalizedId}`;
}

function getActiveConversationStorageKey(sessionIdOverride = null) {
  const rawId = sessionIdOverride ?? state.rcycId ?? (state.mode === "informatica" ? "" : "ANONYMOUS");
  const normalizedId = String(rawId || "").trim().toUpperCase();
  if (!normalizedId) return null;
  return `${ACTIVE_CONVERSATION_PREFIX}:${state.mode}:${normalizedId}`;
}

function getSavedActiveConversationId(sessionIdOverride = null) {
  const key = getActiveConversationStorageKey(sessionIdOverride);
  if (!key) return null;
  const val = safeStorageGet(key);
  return val && val.trim() ? val.trim() : null;
}

function setSavedActiveConversationId(conversationId, sessionIdOverride = null) {
  const key = getActiveConversationStorageKey(sessionIdOverride);
  if (!key) return;
  if (conversationId) {
    safeStorageSet(key, String(conversationId));
  } else {
    safeStorageRemove(key);
  }
}

function clearSavedActiveConversationId(sessionIdOverride = null) {
  const key = getActiveConversationStorageKey(sessionIdOverride);
  if (key) {
    safeStorageRemove(key);
  }
}

function createConversationId() {
  return `conv_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

function sanitizeUiMessages(rawMessages) {
  if (!Array.isArray(rawMessages)) return [];
  return rawMessages
    .filter((m) => m && (m.role === "user" || m.role === "assistant") && typeof m.content === "string")
    .map((m) => ({
      role: m.role,
      content: m.content,
      recommendations: Array.isArray(m.recommendations) ? m.recommendations : [],
      referencedVoyages: Array.isArray(m.referencedVoyages) ? m.referencedVoyages : [],
      timestamp: typeof m.timestamp === "string" && m.timestamp ? m.timestamp : currentTimeStr(),
    }))
    .slice(-MAX_MESSAGES_PER_CONVERSATION);
}

function sanitizeHistoryEntries(rawHistory) {
  if (!Array.isArray(rawHistory)) return [];
  return rawHistory
    .filter((h) => h && (h.role === "user" || h.role === "assistant") && typeof h.content === "string")
    .map((h) => ({
      role: h.role,
      content: h.content,
      voyage_ids: Array.isArray(h.voyage_ids) ? h.voyage_ids.map(String) : [],
    }))
    .slice(-MAX_MESSAGES_PER_CONVERSATION);
}

function stripQuotesAndPiiFromTitle(rawText) {
  let cleaned = String(rawText || "");
  cleaned = cleaned.replace(/\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b/g, " ");
  cleaned = cleaned.replace(/(?:\+?\d[\d\s().\-]{5,}\d)/g, " ");
  cleaned = cleaned.replace(/\b[A-Za-z0-9_-]*\d[A-Za-z0-9_-]*\b|#\w+/g, " ");
  cleaned = cleaned.replace(/["'`“”‘’]+/g, "");
  cleaned = cleaned.replace(/[*_#\[\]{}()<>|]+/g, " ");
  cleaned = cleaned.replace(/\s+/g, " ").replace(/^[ .,:;!?/-]+|[ .,:;!?/-]+$/g, "");
  if (cleaned) {
    cleaned = cleaned.charAt(0).toUpperCase() + cleaned.slice(1);
  }
  return cleaned;
}

function buildClientFallbackTitle(message) {
  const lower = String(message || "").toLowerCase();
  if (
    ["ambassador", "representative", "human", "speak to", "talk to", "complaint", "refund", "dispute", "medical", "allergy", "wheelchair", "accessibility"].some(
      (kw) => lower.includes(kw)
    )
  ) {
    return "Speak to an Ambassador";
  }
  if (
    ["booking", "bookings", "reservation", "reservations", "booked", "sailing date", "sailing dates", "which ship", "what ship", "cabin", "my trip", "my cruise", "my voyage"].some(
      (kw) => lower.includes(kw)
    )
  ) {
    return "My bookings";
  }
  if (["loyalty", "tier", "marriott", "bonvoy", "vip", "membership", "points"].some((kw) => lower.includes(kw))) {
    return "Loyalty tier question";
  }
  if (
    ["best voyage", "recommend", "recommendation", "suggest", "for me", "something different", "which voyage", "pick a voyage", "tailored"].some(
      (kw) => lower.includes(kw)
    )
  ) {
    return "Best voyage recommendation";
  }
  if (["dining", "restaurant", "culinary", "food", "chef", "wine", "cuisine", "dietary"].some((kw) => lower.includes(kw))) {
    return "Dining options";
  }
  if (["spa", "wellness", "massage", "fitness", "salon", "thermal"].some((kw) => lower.includes(kw))) {
    return "Spa and wellness";
  }
  if (["excursion", "excursions", "shore", "tour", "tours", "port", "ports", "adventure"].some((kw) => lower.includes(kw))) {
    return "Shore excursions";
  }
  const regionMap = [
    [["mediterranean"], "Mediterranean voyages"],
    [["caribbean"], "Caribbean voyages"],
    [["alaska"], "Alaska voyages"],
    [["northern europe", "baltic", "norway", "scandinavia", "iceland"], "Northern Europe voyages"],
    [["asia", "japan"], "Asia voyages"],
    [["antarctica"], "Antarctica voyages"],
    [["greek", "greece"], "Greek Isles voyages"],
    [["italy", "italian", "amalfi"], "Italy voyages"],
    [["spain", "spanish"], "Spain voyages"],
    [["france", "french riviera", "riviera"], "French Riviera voyages"],
  ];
  for (const [keywords, title] of regionMap) {
    if (keywords.some((kw) => lower.includes(kw))) {
      return title;
    }
  }
  if (["email", "e-mail", "phone", "telephone", "mobile", "contact"].some((kw) => lower.includes(kw))) {
    return "Contact details question";
  }
  if (["suite", "suites", "penthouse", "terrace", "loft"].some((kw) => lower.includes(kw))) {
    return "Suite options inquiry";
  }
  if (["price", "cost", "fare", "pricing", "rate"].some((kw) => lower.includes(kw))) {
    return "Voyage pricing question";
  }
  if (["yacht", "yachts", "evrima", "ilma", "luminara", "fleet"].some((kw) => lower.includes(kw))) {
    return "Yacht fleet details";
  }
  if (["catalog", "collection", "voyages", "voyage", "itinerary", "itineraries", "cruises"].some((kw) => lower.includes(kw))) {
    return "Voyage collection inquiry";
  }
  return "General question";
}

function formatConversationDateTime(ts) {
  const d = new Date(Number(ts) || Date.now());
  const now = new Date();
  const isToday =
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate();

  if (isToday) {
    const timePart = d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
    return `Today ${timePart}`;
  }
  if (d.getFullYear() === now.getFullYear()) {
    return d.toLocaleDateString([], { month: "short", day: "numeric" });
  }
  return d.toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" });
}

function normalizeConversationsList(list) {
  if (!Array.isArray(list)) return [];
  const normalized = [];
  for (const item of list) {
    if (!item || typeof item !== "object") continue;
    const messages = sanitizeUiMessages(item.messages);
    const firstUserIdx = messages.findIndex(
      (m) => m && m.role === "user" && typeof m.content === "string" && m.content.trim()
    );
    if (firstUserIdx === -1) continue;

    const history = sanitizeHistoryEntries(item.history);
    const updatedAt = Number(item.updatedAt) || Date.now();
    const createdAt = Number(item.createdAt) || updatedAt;

    let title = "New chat";
    let titleGenerated = false;

    if (item.titleGenerated === true) {
      const cleanedSaved = stripQuotesAndPiiFromTitle(item.title);
      if (cleanedSaved && !["new chat", "new conversation"].includes(cleanedSaved.toLowerCase())) {
        title = cleanedSaved;
        titleGenerated = true;
      }
    } else if (typeof item.titleGenerated !== "boolean") {
      const hasReplyAfterFirstUser = messages.slice(firstUserIdx + 1).some((m) => m.role === "assistant");
      if (hasReplyAfterFirstUser) {
        title = buildClientFallbackTitle(messages[firstUserIdx].content);
        titleGenerated = true;
      }
    }

    normalized.push({
      id: typeof item.id === "string" && item.id ? item.id : createConversationId(),
      title,
      titleGenerated,
      createdAt,
      updatedAt,
      messages,
      history,
    });
  }
  normalized.sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0));
  return normalized.slice(0, MAX_CONVERSATIONS_PER_CUSTOMER);
}

function saveConversationsForCustomer(sessionIdOverride = null) {
  const key = getConversationsStorageKey(sessionIdOverride);
  if (!key) return;
  const cleaned = normalizeConversationsList(state.conversations);
  state.conversations = cleaned;
  const payload = {
    version: 1,
    mode: state.mode,
    customerId: String(sessionIdOverride ?? state.rcycId ?? "").trim().toUpperCase(),
    conversations: cleaned,
  };
  try {
    safeStorageSet(key, JSON.stringify(payload));
  } catch (err) {
    // Fallback already handled inside safeStorageSet; guard JSON stringify just in case
  }
}

function loadConversationsForCustomer(sessionIdOverride = null) {
  const convKey = getConversationsStorageKey(sessionIdOverride);
  if (!convKey) return [];

  let conversations = [];
  const rawConv = safeStorageGet(convKey);
  if (rawConv) {
    try {
      const parsed = JSON.parse(rawConv);
      const rawList = Array.isArray(parsed)
        ? parsed
        : parsed && Array.isArray(parsed.conversations)
        ? parsed.conversations
        : [];
      conversations = normalizeConversationsList(rawList);
    } catch (err) {
      safeStorageRemove(convKey);
      conversations = [];
    }
  }

  // Migrate any existing single saved chat into the first conversation
  const legacyKey = getLegacyChatStorageKey(sessionIdOverride);
  if (legacyKey) {
    const rawLegacy = safeStorageGet(legacyKey);
    if (rawLegacy) {
      try {
        const parsedLegacy = JSON.parse(rawLegacy);
        const legacyMessages = sanitizeUiMessages(parsedLegacy && parsedLegacy.messages);
        const firstUserIdx = legacyMessages.findIndex(
          (m) => m && m.role === "user" && typeof m.content === "string" && m.content.trim()
        );
        if (firstUserIdx !== -1) {
          const legacyHistory = sanitizeHistoryEntries(parsedLegacy && parsedLegacy.history);
          const legacyTs = Number(parsedLegacy.updatedAt) || Date.now();
          const hasReply = legacyMessages.slice(firstUserIdx + 1).some((m) => m.role === "assistant");
          const migratedConv = {
            id: createConversationId(),
            title: hasReply ? buildClientFallbackTitle(legacyMessages[firstUserIdx].content) : "New chat",
            titleGenerated: hasReply,
            createdAt: legacyTs,
            updatedAt: legacyTs,
            messages: legacyMessages,
            history: legacyHistory,
          };
          conversations = normalizeConversationsList([migratedConv, ...conversations]);
          state.conversations = conversations;
          saveConversationsForCustomer(sessionIdOverride);
        }
      } catch (err) {
        // Ignore corrupt legacy entry and remove it below
      } finally {
        safeStorageRemove(legacyKey);
      }
    }
  }

  return conversations;
}

function syncActiveConversation({ touchTimestamp = true } = {}) {
  const customerId = String(state.rcycId || "").trim();
  if (!customerId) return;

  const hasUserMsg = state.uiMessages.some((m) => m && m.role === "user" && m.content && m.content.trim());
  if (!hasUserMsg) {
    return;
  }

  const now = Date.now();
  const cappedMessages = state.uiMessages.slice(-MAX_MESSAGES_PER_CONVERSATION);
  const cappedHistory = state.history.slice(-MAX_MESSAGES_PER_CONVERSATION);
  state.uiMessages = cappedMessages;
  state.history = cappedHistory;

  let existingIdx = state.conversations.findIndex((c) => c.id === state.activeConversationId);
  if (existingIdx === -1) {
    const newId = state.activeConversationId || createConversationId();
    state.activeConversationId = newId;
    state.conversations.unshift({
      id: newId,
      title: "New chat",
      titleGenerated: false,
      createdAt: now,
      updatedAt: now,
      messages: [...cappedMessages],
      history: [...cappedHistory],
    });
  } else {
    const prev = state.conversations[existingIdx];
    state.conversations[existingIdx] = {
      ...prev,
      title: prev.title || "New chat",
      titleGenerated: Boolean(prev.titleGenerated),
      updatedAt: touchTimestamp ? now : prev.updatedAt || now,
      messages: [...cappedMessages],
      history: [...cappedHistory],
    };
  }

  setSavedActiveConversationId(state.activeConversationId, customerId);
  saveConversationsForCustomer(customerId);
  renderHistorySidebar();
}

function setConversationTitleOnce(conversationId, candidateTitle) {
  if (!conversationId) return;
  const idx = state.conversations.findIndex((c) => c.id === conversationId);
  if (idx === -1) return;
  const target = state.conversations[idx];
  if (target.titleGenerated) return;

  const cleaned = stripQuotesAndPiiFromTitle(candidateTitle);
  const finalTitle =
    cleaned && !["new chat", "new conversation"].includes(cleaned.toLowerCase())
      ? cleaned
      : "General question";

  state.conversations[idx] = {
    ...target,
    title: finalTitle,
    titleGenerated: true,
  };
  saveConversationsForCustomer();
  renderHistorySidebar();
}

async function requestConversationTitle(firstGuestMessage) {
  const fallback = buildClientFallbackTitle(firstGuestMessage);
  try {
    const res = await apiFetch("/api/conversations/title", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: firstGuestMessage }),
    });
    if (!res.ok) return fallback;
    const data = await res.json().catch(() => ({}));
    const cleaned = typeof data.title === "string" ? stripQuotesAndPiiFromTitle(data.title) : "";
    if (!cleaned || ["new chat", "new conversation"].includes(cleaned.toLowerCase())) {
      return fallback;
    }
    return cleaned;
  } catch (err) {
    return fallback;
  }
}

function isMobileViewport() {
  return typeof window !== "undefined" && window.innerWidth <= MOBILE_BREAKPOINT_PX;
}

function getSidebarStorageKey(mobile = isMobileViewport()) {
  return mobile ? SIDEBAR_OPEN_MOBILE_KEY : SIDEBAR_OPEN_DESKTOP_KEY;
}

function getSavedSidebarOpen(mobile = isMobileViewport()) {
  const raw = safeStorageGet(getSidebarStorageKey(mobile));
  if (raw === "true") return true;
  if (raw === "false") return false;
  return !mobile;
}

function applySidebarOpenState(isOpen, { persist = false } = {}) {
  const mobile = isMobileViewport();
  const open = Boolean(isOpen);
  state.sidebarOpen = open;

  if (persist) {
    safeStorageSet(getSidebarStorageKey(mobile), open ? "true" : "false");
  }

  if (el.workspaceMain) {
    el.workspaceMain.classList.toggle("is-sidebar-collapsed", !mobile && !open);
  }
  if (el.historySidebar && el.historyDrawerBackdrop) {
    if (mobile && open) {
      el.historySidebar.classList.add("is-open-mobile");
      el.historyDrawerBackdrop.classList.remove("hidden");
    } else {
      el.historySidebar.classList.remove("is-open-mobile");
      el.historyDrawerBackdrop.classList.add("hidden");
    }
  }
  if (el.sidebarToggleBtn) {
    el.sidebarToggleBtn.setAttribute("aria-expanded", String(open));
    el.sidebarToggleBtn.setAttribute(
      "aria-label",
      open ? "Close conversation history" : "Open conversation history"
    );
  }
}

function closeHistoryDrawer({ persist = false } = {}) {
  if (isMobileViewport()) {
    applySidebarOpenState(false, { persist });
  } else if (el.historySidebar && el.historyDrawerBackdrop) {
    el.historySidebar.classList.remove("is-open-mobile");
    el.historyDrawerBackdrop.classList.add("hidden");
  }
}

function renderHistorySidebar() {
  if (!el.historyList) return;
  el.historyList.innerHTML = "";

  if (!Array.isArray(state.conversations) || state.conversations.length === 0) {
    const empty = document.createElement("div");
    empty.className = "history-empty";
    empty.textContent = "No conversations yet.";
    el.historyList.appendChild(empty);
    return;
  }

  for (const conv of state.conversations) {
    const item = document.createElement("div");
    item.className = "history-item";
    item.setAttribute("role", "listitem");
    if (conv.id === state.activeConversationId) {
      item.classList.add("is-active");
    }
    if (state.pendingDeleteConversationId === conv.id) {
      item.classList.add("is-confirming-delete");
    }

    const mainRow = document.createElement("div");
    mainRow.className = "history-item-main";

    const displayTitle = stripQuotesAndPiiFromTitle(conv.title) || "New chat";

    const selectBtn = document.createElement("button");
    selectBtn.type = "button";
    selectBtn.className = "history-item-select";
    selectBtn.setAttribute("aria-current", conv.id === state.activeConversationId ? "true" : "false");

    const titleEl = document.createElement("span");
    titleEl.className = "history-item-title";
    titleEl.textContent = displayTitle;
    titleEl.title = displayTitle;

    const timeEl = document.createElement("span");
    timeEl.className = "history-item-time";
    timeEl.textContent = formatConversationDateTime(conv.updatedAt);

    selectBtn.appendChild(titleEl);
    selectBtn.appendChild(timeEl);
    selectBtn.addEventListener("click", () => {
      loadConversationById(conv.id);
      if (isMobileViewport()) {
        applySidebarOpenState(false, { persist: false });
      }
    });

    const delBtn = document.createElement("button");
    delBtn.type = "button";
    delBtn.className = "history-delete-btn";
    delBtn.setAttribute("aria-label", `Delete conversation ${displayTitle}`);
    delBtn.title = "Delete conversation";
    delBtn.innerHTML = `
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <polyline points="3 6 5 6 21 6"/>
        <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>
        <path d="M10 11v6"/>
        <path d="M14 11v6"/>
        <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>
      </svg>
    `;
    delBtn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      state.pendingDeleteConversationId =
        state.pendingDeleteConversationId === conv.id ? null : conv.id;
      renderHistorySidebar();
    });

    mainRow.appendChild(selectBtn);
    mainRow.appendChild(delBtn);
    item.appendChild(mainRow);

    if (state.pendingDeleteConversationId === conv.id) {
      const confirmBar = document.createElement("div");
      confirmBar.className = "history-confirm-bar";

      const promptSpan = document.createElement("span");
      promptSpan.textContent = "Delete?";

      const actions = document.createElement("div");
      actions.className = "history-confirm-actions";

      const yesBtn = document.createElement("button");
      yesBtn.type = "button";
      yesBtn.className = "history-confirm-yes";
      yesBtn.textContent = "Delete";
      yesBtn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        deleteConversationById(conv.id);
      });

      const noBtn = document.createElement("button");
      noBtn.type = "button";
      noBtn.className = "history-confirm-no";
      noBtn.textContent = "Cancel";
      noBtn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        state.pendingDeleteConversationId = null;
        renderHistorySidebar();
      });

      actions.appendChild(yesBtn);
      actions.appendChild(noBtn);
      confirmBar.appendChild(promptSpan);
      confirmBar.appendChild(actions);
      item.appendChild(confirmBar);
    }

    el.historyList.appendChild(item);
  }
}

function buildWelcomeTextForCurrentUser() {
  if (state.mode === "informatica") {
    const me = state.me;
    return me && me.first_name
      ? `Welcome, **${me.first_name}**! How may I assist you with your bookings or our voyage collection today?`
      : "Welcome to **MARIS**, your personal yacht concierge for The Ritz-Carlton Yacht Collection. How may I assist you today?";
  }
  const profile = state.profile || ANONYMOUS_FALLBACK_PROFILE;
  if (profile.guest_status === "anonymous") {
    return "Hello and welcome to **MARIS**, your personal yacht concierge for The Ritz-Carlton Yacht Collection. How may I assist you today?";
  }
  if (profile.guest_status === "new") {
    return `Hello, **${profile.first_name}**! Welcome to The Ritz-Carlton Yacht Collection. How may I assist you as you plan your inaugural voyage?`;
  }
  if (!profile.personalization_consent) {
    return "Hello! Personalization is currently off on your profile, so I can assist with general voyage information or connect you with an Experience Ambassador.";
  }
  return `Welcome back, **${profile.first_name}**! How may I assist you with your upcoming journey or our voyage collection today?`;
}

function startNewConversation() {
  state.activeConversationId = null;
  state.pendingDeleteConversationId = null;
  state.history = [];
  state.uiMessages = [];
  clearSavedActiveConversationId();
  el.chatMessages.innerHTML = "";
  if (state.mode === "informatica") {
    renderEscalation(null);
  }
  const welcomeContent = buildWelcomeTextForCurrentUser();
  const welcomeMsg = {
    role: "assistant",
    content: welcomeContent,
    recommendations: [],
    referencedVoyages: [],
    timestamp: currentTimeStr(),
  };
  state.uiMessages.push(welcomeMsg);
  appendMessage(welcomeMsg, { persist: false });
  renderHistorySidebar();
  if (isMobileViewport()) {
    applySidebarOpenState(false, { persist: false });
  }
  if (el.messageInput) {
    el.messageInput.focus();
  }
}

function loadConversationById(conversationId) {
  const conv = state.conversations.find((c) => c.id === conversationId);
  if (!conv) return;
  state.activeConversationId = conv.id;
  state.pendingDeleteConversationId = null;
  setSavedActiveConversationId(conv.id);
  state.history = sanitizeHistoryEntries(conv.history);
  state.uiMessages = sanitizeUiMessages(conv.messages);
  el.chatMessages.innerHTML = "";
  for (const msg of state.uiMessages) {
    appendMessage(msg, { persist: false });
  }
  renderHistorySidebar();
}

function deleteConversationById(conversationId) {
  const wasActive = state.activeConversationId === conversationId;
  state.conversations = state.conversations.filter((c) => c.id !== conversationId);
  state.pendingDeleteConversationId = null;
  saveConversationsForCustomer();

  if (wasActive) {
    if (state.conversations.length > 0) {
      loadConversationById(state.conversations[0].id);
    } else {
      startNewConversation();
    }
  } else {
    renderHistorySidebar();
  }
}

function escapeHtml(text) {
  return String(text ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/**
 * Safely renders limited inline markdown (**bold**, *italic*, `code`) into DOM nodes
 * without allowing any raw HTML injection.
 */
function appendFormattedInline(parentEl, rawText) {
  const tokenRegex = /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g;
  let lastIndex = 0;
  let match;

  while ((match = tokenRegex.exec(rawText)) !== null) {
    if (match.index > lastIndex) {
      parentEl.appendChild(document.createTextNode(rawText.slice(lastIndex, match.index)));
    }
    const token = match[0];
    let node;
    if (token.startsWith("**") && token.endsWith("**")) {
      node = document.createElement("strong");
      node.textContent = token.slice(2, -2);
    } else if (token.startsWith("*") && token.endsWith("*")) {
      node = document.createElement("em");
      node.textContent = token.slice(1, -1);
    } else {
      node = document.createElement("code");
      node.className = "mono";
      node.textContent = token.slice(1, -1);
    }
    parentEl.appendChild(node);
    lastIndex = tokenRegex.lastIndex;
  }

  if (lastIndex < rawText.length) {
    parentEl.appendChild(document.createTextNode(rawText.slice(lastIndex)));
  }
}

function buildSanitizedMessageFragment(rawText) {
  const frag = document.createDocumentFragment();
  const lines = String(rawText ?? "").split("\n");
  let activeList = null;

  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed.startsWith("- ") || trimmed.startsWith("* ") || /^\d+\.\s+/.test(trimmed)) {
      if (!activeList) {
        activeList = document.createElement("ul");
        frag.appendChild(activeList);
      }
      const li = document.createElement("li");
      const itemText = trimmed.replace(/^[-*]\s+/, "").replace(/^\d+\.\s+/, "");
      appendFormattedInline(li, itemText);
      activeList.appendChild(li);
    } else {
      if (activeList) {
        activeList = null;
      }
      if (trimmed) {
        const p = document.createElement("p");
        appendFormattedInline(p, trimmed);
        frag.appendChild(p);
      }
    }
  }
  return frag;
}

function formatCurrency(value) {
  return `$${Number(value || 0).toLocaleString("en-US")}`;
}

function renderProfile(profile, bookings = [], escalation = null) {
  state.profile = profile;
  state.bookings = bookings || [];

  const isAnon = profile.guest_status === "anonymous";
  const isKnown = profile.guest_status === "returning" || profile.guest_status === "new";
  const consentOn = Boolean(isKnown && profile.personalization_consent);

  el.headerGreeting.textContent = isAnon ? "Welcome" : `Welcome, ${profile.first_name}`;
  el.profileKicker.textContent = isAnon ? "Visitor Details" : "Guest Details";
  el.profileName.textContent = isAnon
    ? "Anonymous Visitor"
    : `${profile.first_name} ${profile.last_name}`.trim();

  el.profileStatusSubtitle.textContent = isAnon
    ? "Browsing without profile"
    : profile.guest_status === "new"
    ? `New Guest · ${profile.loyalty_tier}`
    : `Returning Guest · ${profile.loyalty_tier}`;

  el.vipBadge.classList.add("hidden");
  el.profileRcycId.textContent = profile.rcyc_id;

  // Consent = No: panel explicitly shows "Personalization is off" and hides personalized history
  el.consentOffNotice.classList.toggle("hidden", !(isKnown && !consentOn));

  if (isAnon) {
    el.attrConsent.textContent = "Personalization is off";
    el.attrPreferredRegions.textContent = "Not set";
    el.attrSuiteAncillary.textContent = "Not set";
    el.metricVoyages.textContent = "0";
    el.attrPrevRegion.textContent = "None";
    el.metricBooking.textContent = "None";
    el.specialNotesRow.classList.add("hidden");
    el.complaintRow.classList.add("hidden");
  } else if (!consentOn) {
    el.attrConsent.textContent = "No · Personalization is off";
    el.attrPreferredRegions.textContent = "Hidden (personalization off)";
    el.attrSuiteAncillary.textContent = "Hidden (personalization off)";
    el.metricVoyages.textContent = "Hidden";
    el.attrPrevRegion.textContent = "Hidden";
    el.metricBooking.textContent = "Hidden";
    el.specialNotesRow.classList.add("hidden");
    el.complaintRow.classList.add("hidden");
  } else {
    el.attrConsent.textContent = "Yes";
    el.attrPreferredRegions.textContent =
      (profile.preferred_destinations || []).join(", ") || "None";

    const ancillaryStr = (profile.ancillary_purchase_preferences || []).join(", ");
    el.attrSuiteAncillary.textContent = ancillaryStr
      ? `${profile.preferred_suite} · ${ancillaryStr}`
      : profile.preferred_suite || "Not specified";

    el.metricVoyages.textContent = String(profile.past_voyages ?? 0);
    el.attrPrevRegion.textContent = profile.previous_voyage_region || "None";

    if (state.bookings.length === 0) {
      el.metricBooking.textContent = "None";
    } else if (state.bookings.length === 1) {
      el.metricBooking.textContent = `${state.bookings[0].booking_id} (${state.bookings[0].voyage_id})`;
    } else {
      el.metricBooking.textContent = `${state.bookings.length} bookings (${state.bookings
        .map((b) => b.booking_id)
        .join(", ")})`;
    }

    el.specialNotesRow.classList.add("hidden");

    const hasOpenComplaint = Boolean(profile.open_complaint_status || escalation === true || escalation?.escalated);
    if (hasOpenComplaint) {
      el.complaintRow.classList.remove("hidden");
      el.attrComplaint.textContent = "Open service inquiry on file — Experience Ambassador available";
    } else {
      el.complaintRow.classList.add("hidden");
    }
  }

  const normalizedEsc =
    typeof escalation === "boolean"
      ? escalation
        ? {
            escalated: true,
            reason: "Open service inquiry on file requiring Experience Ambassador follow-up.",
            handoff_note: "I've noted this for an Experience Ambassador; in this prototype no notification is sent yet.",
            context_packet: null,
          }
        : null
      : escalation;
  renderEscalation(normalizedEsc);
}

function renderEscalation(escalation) {
  if (escalation && escalation.escalated) {
    el.escalationBanner.classList.remove("hidden");
    el.escalationReasonText.textContent = escalation.reason;
    el.escalationNoteText.textContent = escalation.handoff_note;
    if (escalation.context_packet) {
      el.toggleContextPacketBtn.classList.remove("hidden");
      el.escalationPacketPre.textContent = JSON.stringify(escalation.context_packet, null, 2);
    } else {
      el.toggleContextPacketBtn.classList.add("hidden");
      el.escalationPacketPre.classList.add("hidden");
      el.escalationPacketPre.textContent = "";
    }

    el.profileEscalationBadge.textContent = "Escalated to an Experience Ambassador";
    el.profileEscalationBadge.className = "status-pill-escalated";
    el.profileEscalationDetail.textContent = escalation.reason;
    el.profileEscalationDetail.classList.remove("hidden");

    el.conciergeStatusIndicator.classList.add("is-escalated");
    el.conciergeStatusText.textContent = "Ambassador Requested";
  } else {
    el.escalationBanner.classList.add("hidden");
    el.escalationPacketPre.classList.add("hidden");
    el.profileEscalationBadge.textContent = "None";
    el.profileEscalationBadge.className = "status-pill-nominal";
    el.profileEscalationDetail.classList.add("hidden");

    el.conciergeStatusIndicator.classList.remove("is-escalated");
    el.conciergeStatusText.textContent = "Concierge Online";
  }
}

function updateDemoInsights(data = null) {
  if (!data) {
    el.insightEngineText.textContent = "Awaiting inquiry…";
    el.usedFieldsList.textContent = "None";
    el.insightScoreBreakdown.textContent = "No active scored recommendations.";
    return;
  }

  const engineLabel = data.llm_provider_used || "rule_based";
  const fallbackNote = data.llm_fallback_triggered ? " (fallback)" : "";
  const consentLabel = data.consent_applied ? "Personalization Active" : "Personalization Off";
  el.insightEngineText.textContent = `${engineLabel}${fallbackNote} · ${consentLabel}`;

  el.usedFieldsList.textContent =
    data.used_profile_fields && data.used_profile_fields.length > 0
      ? data.used_profile_fields.join(" · ")
      : "None (0 profile fields used)";

  el.insightScoreBreakdown.innerHTML = "";
  if (data.recommendations && data.recommendations.length > 0) {
    for (const rec of data.recommendations) {
      const row = document.createElement("div");
      row.className = "insight-score-row";

      const title = document.createElement("strong");
      title.textContent = `${rec.voyage.voyage_id} (${rec.voyage.voyage_name}): ${rec.score}/100`;

      const bd = rec.score_breakdown || {};
      const detail = document.createElement("span");
      detail.className = "mono";
      detail.textContent = `region:+${bd.preferred_region ?? 0} · focus:+${bd.interest_focus ?? 0} · suite:+${bd.preferred_suite_availability ?? 0} · new_region:+${bd.new_region_vs_last_voyage ?? 0}`;

      row.appendChild(title);
      row.appendChild(detail);
      el.insightScoreBreakdown.appendChild(row);
    }
  } else {
    el.insightScoreBreakdown.textContent = "No scored recommendations in last turn.";
  }
}

function createMarisAvatar() {
  const wrap = document.createElement("div");
  wrap.className = "maris-avatar";
  wrap.innerHTML = `
    <svg width="22" height="22" viewBox="0 0 36 36" fill="none" aria-hidden="true">
      <path d="M18 5L29 24H18V5Z" fill="#C9A255"/>
      <path d="M16 9L8 24H16V9Z" fill="#C9A255" fill-opacity="0.82"/>
      <path d="M5 26.5H31L27.5 30.5H8.5L5 26.5Z" fill="#C9A255"/>
    </svg>
  `;
  return wrap;
}

function appendMessage(
  { role, content, recommendations = [], referencedVoyages = [], timestamp = null },
  { persist = true } = {}
) {
  const timeStr = timestamp || currentTimeStr();
  const row = document.createElement("div");
  row.className = `message-row ${role}`;

  if (role === "user") {
    const bubble = document.createElement("div");
    bubble.className = "user-bubble";

    const span = document.createElement("span");
    span.textContent = content;
    const timeEl = document.createElement("span");
    timeEl.className = "user-bubble-time";
    timeEl.textContent = timeStr;

    bubble.appendChild(span);
    bubble.appendChild(timeEl);
    row.appendChild(bubble);
  } else {
    row.appendChild(createMarisAvatar());
    const col = document.createElement("div");
    col.className = "assistant-col";

    const header = document.createElement("div");
    header.className = "assistant-header";
    const nameEl = document.createElement("span");
    nameEl.className = "assistant-name";
    nameEl.textContent = "MARIS";
    const timeEl = document.createElement("span");
    timeEl.className = "msg-time";
    timeEl.textContent = timeStr;
    header.appendChild(nameEl);
    header.appendChild(timeEl);
    col.appendChild(header);

    const bubble = document.createElement("div");
    bubble.className = "assistant-bubble";
    bubble.appendChild(buildSanitizedMessageFragment(content));

    const cardsToRender =
      recommendations && recommendations.length > 0
        ? recommendations.map((r) => r.voyage)
        : referencedVoyages || [];

    if (cardsToRender.length > 0) {
      const cardsRow = document.createElement("div");
      cardsRow.className = "voyage-cards-row";

      for (const v of cardsToRender) {
        const cardBtn = document.createElement("button");
        cardBtn.type = "button";
        cardBtn.className = "voyage-mini-card";

        const leftDiv = document.createElement("div");
        leftDiv.className = "voyage-mini-left";

        const tileDiv = document.createElement("div");
        tileDiv.className = "voyage-sail-tile";
        tileDiv.setAttribute("aria-hidden", "true");
        tileDiv.innerHTML = `
          <svg width="24" height="24" viewBox="0 0 36 36" fill="none">
            <path d="M18 6L28 24H18V6Z" fill="#7D9BBF"/>
            <path d="M16 10L9 24H16V10Z" fill="#9EB7D4"/>
            <path d="M6 26H30L27 29.5H9L6 26Z" fill="#7D9BBF"/>
          </svg>
        `;

        const infoDiv = document.createElement("div");
        infoDiv.className = "voyage-mini-info";

        const titleDiv = document.createElement("div");
        titleDiv.className = "voyage-mini-title";
        titleDiv.textContent = v.voyage_name;

        const subDiv = document.createElement("div");
        subDiv.className = "voyage-mini-sub";
        subDiv.textContent = `${v.duration} nights | From ${formatCurrency(v.price)} per guest`;

        const metaDiv = document.createElement("div");
        metaDiv.className = "voyage-mini-meta";
        metaDiv.textContent = `${v.voyage_id} · ${v.destination} · ${v.yacht_name}`;

        infoDiv.appendChild(titleDiv);
        infoDiv.appendChild(subDiv);
        infoDiv.appendChild(metaDiv);

        leftDiv.appendChild(tileDiv);
        leftDiv.appendChild(infoDiv);

        const chevron = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        chevron.setAttribute("class", "voyage-chevron");
        chevron.setAttribute("width", "18");
        chevron.setAttribute("height", "18");
        chevron.setAttribute("viewBox", "0 0 24 24");
        chevron.setAttribute("fill", "none");
        chevron.setAttribute("stroke", "currentColor");
        chevron.setAttribute("stroke-width", "2");
        chevron.setAttribute("stroke-linecap", "round");
        chevron.setAttribute("stroke-linejoin", "round");
        chevron.setAttribute("aria-hidden", "true");
        chevron.innerHTML = '<polyline points="9 18 15 12 9 6"></polyline>';

        cardBtn.appendChild(leftDiv);
        cardBtn.appendChild(chevron);

        cardBtn.addEventListener("click", () => {
          sendMessage(`Tell me the highlights and suite options for ${v.voyage_id} (${v.voyage_name}).`);
        });
        cardsRow.appendChild(cardBtn);
      }

      bubble.appendChild(cardsRow);
    }

    col.appendChild(bubble);
    row.appendChild(col);
  }

  el.chatMessages.appendChild(row);
  el.chatMessages.scrollTop = el.chatMessages.scrollHeight;

  if (persist) {
    state.uiMessages.push({
      role,
      content,
      recommendations: Array.isArray(recommendations) ? recommendations : [],
      referencedVoyages: Array.isArray(referencedVoyages) ? referencedVoyages : [],
      timestamp: timeStr,
    });
    syncActiveConversation({ touchTimestamp: true });
  }
}

function renderWelcomeMessage(profile) {
  state.profile = profile;
  state.pendingDeleteConversationId = null;
  const loaded = loadConversationsForCustomer(profile.rcyc_id);
  state.conversations = loaded;
  const savedActiveId = getSavedActiveConversationId(profile.rcyc_id);
  if (savedActiveId && loaded.some((c) => c.id === savedActiveId)) {
    loadConversationById(savedActiveId);
    return;
  }
  startNewConversation();
}

function syncSelects(value) {
  if ([...el.guestSelect.options].some((o) => o.value === value)) {
    el.guestSelect.value = value;
  }
  if ([...el.inlineGuestSelect.options].some((o) => o.value === value)) {
    el.inlineGuestSelect.value = value;
  }
}

function setGuestListUnavailableUI() {
  state.guestListAvailable = false;
  state.sampleIds = new Set(["ANONYMOUS"]);

  const populateUnavailable = (selectEl) => {
    selectEl.innerHTML = "";
    const anonOpt = document.createElement("option");
    anonOpt.value = "ANONYMOUS";
    anonOpt.textContent = "Anonymous Visitor";
    const statusOpt = document.createElement("option");
    statusOpt.value = "";
    statusOpt.disabled = true;
    statusOpt.textContent = "Guest list unavailable";
    selectEl.appendChild(anonOpt);
    selectEl.appendChild(statusOpt);
    selectEl.value = "ANONYMOUS";
  };

  populateUnavailable(el.guestSelect);
  populateUnavailable(el.inlineGuestSelect);
  el.idLookupFeedback.textContent = "Guest list unavailable";
  el.idLookupFeedback.classList.remove("hidden");
}

async function loadGuestsDropdown() {
  try {
    const res = await apiFetch("/api/guests");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const guests = await res.json();
    if (!Array.isArray(guests)) throw new Error("Invalid guest list response");

    state.guestListAvailable = true;
    state.sampleIds = new Set(["ANONYMOUS"]);
    const populate = (selectEl) => {
      selectEl.innerHTML = '<option value="ANONYMOUS">Anonymous Visitor</option>';
      for (const g of guests) {
        state.sampleIds.add(g.rcyc_id.toUpperCase());
        const opt = document.createElement("option");
        opt.value = g.rcyc_id;
        const labelSuffix = g.profile_label ? ` · ${g.profile_label}` : "";
        opt.textContent = `${g.rcyc_id} · ${g.full_name} (${g.loyalty_tier}${labelSuffix})`;
        selectEl.appendChild(opt);
      }
    };

    populate(el.guestSelect);
    populate(el.inlineGuestSelect);
    el.idLookupFeedback.classList.add("hidden");
    return guests;
  } catch (err) {
    setGuestListUnavailableUI();
    return null;
  }
}

async function selectGuest(rcycId) {
  const cleanId = (rcycId || "ANONYMOUS").trim().toUpperCase();
  if (state.guestListAvailable) {
    el.idLookupFeedback.classList.add("hidden");
  } else {
    el.idLookupFeedback.textContent = "Guest list unavailable";
    el.idLookupFeedback.classList.remove("hidden");
  }

  if (!state.sampleIds.has(cleanId)) {
    el.idLookupFeedback.textContent = state.guestListAvailable
      ? "ID not found"
      : "Guest list unavailable";
    el.idLookupFeedback.classList.remove("hidden");
    return false;
  }

  state.rcycId = cleanId;
  try {
    const res = await apiFetch(`/api/guests/${encodeURIComponent(cleanId)}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    if (data.status === "not_found" || !data.profile) {
      el.idLookupFeedback.textContent = "ID not found";
      el.idLookupFeedback.classList.remove("hidden");
      return false;
    }

    safeStorageSet(ACTIVE_MOCK_GUEST_KEY, cleanId);
    syncSelects(cleanId);
    updateDemoInsights(null);
    renderProfile(data.profile, data.bookings, Boolean(data.escalation));
    renderWelcomeMessage(data.profile);
    return true;
  } catch (err) {
    if (cleanId === "ANONYMOUS") {
      safeStorageSet(ACTIVE_MOCK_GUEST_KEY, "ANONYMOUS");
      syncSelects("ANONYMOUS");
      updateDemoInsights(null);
      renderProfile(ANONYMOUS_FALLBACK_PROFILE, [], null);
      renderWelcomeMessage(ANONYMOUS_FALLBACK_PROFILE);
      return true;
    }
    el.idLookupFeedback.textContent = state.guestListAvailable
      ? "ID not found"
      : "Guest list unavailable";
    el.idLookupFeedback.classList.remove("hidden");
    return false;
  }
}

function configureMockChrome() {
  el.chatIdentityStrip.classList.remove("hidden");
  el.guestPickerSection.classList.remove("hidden");
  el.guestPickerDivider.classList.remove("hidden");
  el.popoverSwitchAnonBtn.classList.remove("hidden");
  el.popoverLogoutBtn.classList.add("hidden");
  el.demoInsightsToggleBtn.classList.remove("hidden");
  el.demoFooter.classList.remove("hidden");
  el.demoConsentNotice.classList.add("hidden");
  el.rowInfaLoyalty.classList.add("hidden");
  el.rowInfaEmail.classList.add("hidden");
  el.rowInfaPhone.classList.add("hidden");
  hideLoginView();
}

function configureInformaticaChrome() {
  el.chatIdentityStrip.classList.add("hidden");
  el.guestPickerSection.classList.add("hidden");
  el.guestPickerDivider.classList.add("hidden");
  el.popoverSwitchAnonBtn.classList.add("hidden");
  el.popoverLogoutBtn.classList.remove("hidden");
  el.demoInsightsToggleBtn.classList.add("hidden");
  el.demoInsightsDrawer.classList.add("hidden");
  el.demoFooter.classList.add("hidden");
}

function resetPasswordToggle() {
  el.loginPassword.type = "password";
  if (el.togglePasswordBtn) {
    el.togglePasswordBtn.textContent = "Show";
    el.togglePasswordBtn.setAttribute("aria-label", "Show password");
    el.togglePasswordBtn.setAttribute("aria-pressed", "false");
  }
}

function showLoginView(errorMsg = "") {
  el.infaLoginView.classList.remove("hidden");
  el.workspaceMain.classList.add("hidden");
  if (el.sidebarToggleBtn) el.sidebarToggleBtn.classList.add("hidden");
  el.accountMenuBtn.classList.add("hidden");
  el.catalogTriggerBtn.classList.add("hidden");
  el.demoInsightsToggleBtn.classList.add("hidden");
  el.demoInsightsDrawer.classList.add("hidden");
  el.demoFooter.classList.add("hidden");
  closeHistoryDrawer();
  resetPasswordToggle();
  closePopover();
  if (errorMsg) {
    el.loginError.textContent = errorMsg;
    el.loginError.classList.remove("hidden");
  } else {
    el.loginError.classList.add("hidden");
  }
}

function hideLoginView() {
  el.infaLoginView.classList.add("hidden");
  el.workspaceMain.classList.remove("hidden");
  if (el.sidebarToggleBtn) el.sidebarToggleBtn.classList.remove("hidden");
  el.accountMenuBtn.classList.remove("hidden");
  el.catalogTriggerBtn.classList.remove("hidden");
  el.loginError.classList.add("hidden");
  applySidebarOpenState(getSavedSidebarOpen(), { persist: false });
}

function formatBookedOnDate(dateStr) {
  if (!dateStr) return "";
  const parsed = new Date(dateStr);
  if (isNaN(parsed.getTime())) return dateStr;
  const day = String(parsed.getDate()).padStart(2, "0");
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const mon = months[parsed.getMonth()];
  const yr = parsed.getFullYear();
  return `${day} ${mon} ${yr}`;
}

function buildInfaBookingsFragment(bookingsList) {
  const frag = document.createDocumentFragment();
  const bookings = Array.isArray(bookingsList) ? bookingsList : [];
  if (bookings.length === 0) {
    const empty = document.createElement("div");
    empty.className = "kv-row";
    const key = document.createElement("span");
    key.className = "kv-key";
    key.textContent = "Bookings";
    const val = document.createElement("span");
    val.className = "kv-val";
    val.textContent = "None on file";
    empty.appendChild(key);
    empty.appendChild(val);
    frag.appendChild(empty);
    return frag;
  }

  for (const b of bookings) {
    const block = document.createElement("div");
    block.className = "kv-table infa-booking-block";
    block.style.marginBottom = "0.75rem";

    const fields = [["Booking ID", b.booking_id, "mono"]];
    if (b.voyage_name) {
      fields.push(["Voyage", b.voyage_name, ""]);
      if (b.destination) fields.push(["Destination", b.destination, ""]);
    }
    if (b.booking_date) {
      fields.push(["Booked on", formatBookedOnDate(b.booking_date), "mono"]);
    }

    for (const [label, value, cls] of fields) {
      if (value === undefined || value === null || value === "") continue;
      const row = document.createElement("div");
      row.className = "kv-row";
      const k = document.createElement("span");
      k.className = "kv-key";
      k.textContent = label;
      const v = document.createElement("span");
      v.className = cls ? `kv-val ${cls}` : "kv-val";
      v.textContent = String(value);
      row.appendChild(k);
      row.appendChild(v);
      block.appendChild(row);
    }

    const statusCode = b.status_code !== undefined && b.status_code !== null && b.status_code !== ""
      ? String(b.status_code)
      : "";
    if (statusCode) {
      const row = document.createElement("div");
      row.className = "kv-row";
      const k = document.createElement("span");
      k.className = "kv-key";
      k.textContent = "Status";
      const v = document.createElement("span");
      v.className = "status-code-pill";
      v.textContent = statusCode;
      row.appendChild(k);
      row.appendChild(v);
      block.appendChild(row);
    }

    frag.appendChild(block);
  }
  return frag;
}

function renderInformaticaMe(me) {
  state.me = me;
  state.rcycId = me.customer_id || "";
  state.bookings = Array.isArray(me.bookings) ? me.bookings : [];

  el.headerGreeting.textContent = me.first_name ? `Welcome, ${me.first_name}` : "Welcome";
  el.profileKicker.textContent = "Guest Details";
  el.profileName.textContent = me.full_name || me.first_name || "Guest";

  if (me.loyalty_tier) {
    el.profileStatusSubtitle.textContent = me.loyalty_tier;
    el.profileStatusSubtitle.classList.remove("hidden");
    el.rowInfaLoyalty.classList.remove("hidden");
    el.attrInfaLoyalty.textContent = me.loyalty_tier;
  } else {
    el.profileStatusSubtitle.textContent = "";
    el.profileStatusSubtitle.classList.add("hidden");
    el.rowInfaLoyalty.classList.add("hidden");
  }

  el.vipBadge.classList.toggle("hidden", me.vip_status !== true);
  el.consentOffNotice.classList.add("hidden");
  el.demoConsentNotice.classList.toggle("hidden", me.demo_consent_assumed !== true);

  el.profileIdLabel.textContent = "Customer ID";
  el.profileRcycId.textContent = me.customer_id || "";

  if (me.email) {
    el.rowInfaEmail.classList.remove("hidden");
    el.attrInfaEmail.textContent = me.email;
  } else {
    el.rowInfaEmail.classList.add("hidden");
  }

  if (me.phone) {
    el.rowInfaPhone.classList.remove("hidden");
    el.attrInfaPhone.textContent = me.phone;
  } else {
    el.rowInfaPhone.classList.add("hidden");
  }

  if (me.consent_configured === true) {
    el.rowConsent.classList.remove("hidden");
    el.attrConsent.textContent = me.personalization_consent ? "Yes" : "No · Personalization is off";
  } else {
    el.rowConsent.classList.add("hidden");
  }

  if (Array.isArray(me.preferred_destinations) && me.preferred_destinations.length > 0) {
    el.rowPreferredRegions.classList.remove("hidden");
    el.attrPreferredRegions.textContent = me.preferred_destinations.join(", ");
  } else {
    el.rowPreferredRegions.classList.add("hidden");
  }

  const suiteParts = [];
  if (me.preferred_suite) suiteParts.push(me.preferred_suite);
  if (Array.isArray(me.interest_focus) && me.interest_focus.length > 0) {
    suiteParts.push(me.interest_focus.join(", "));
  }
  if (suiteParts.length > 0) {
    el.rowSuiteAncillary.classList.remove("hidden");
    el.attrSuiteAncillary.textContent = suiteParts.join(" · ");
  } else {
    el.rowSuiteAncillary.classList.add("hidden");
  }

  el.specialNotesRow.classList.add("hidden");

  if (me.open_complaint_status === true) {
    el.complaintRow.classList.remove("hidden");
    el.attrComplaint.textContent = "Open service inquiry on file — Experience Ambassador available";
  } else {
    el.complaintRow.classList.add("hidden");
  }

  el.mockBookingsTable.classList.add("hidden");
  el.infaBookingsList.classList.remove("hidden");
  el.profileEscalationDetail.classList.add("hidden");

  el.infaBookingsList.innerHTML = "";
  el.infaBookingsList.appendChild(buildInfaBookingsFragment(me.bookings));
}

function renderInformaticaWelcome(me, { isFreshLogin = false } = {}) {
  state.me = me;
  state.pendingDeleteConversationId = null;
  if (me && me.customer_id) {
    state.conversations = loadConversationsForCustomer(me.customer_id);
    if (isFreshLogin) {
      clearSavedActiveConversationId(me.customer_id);
    } else {
      const savedActiveId = getSavedActiveConversationId(me.customer_id);
      if (savedActiveId && state.conversations.some((c) => c.id === savedActiveId)) {
        loadConversationById(savedActiveId);
        return;
      }
    }
  } else {
    state.conversations = [];
  }
  startNewConversation();
}

function createModalKvRow(label, value, valueClass = "") {
  const row = document.createElement("div");
  row.className = "kv-row";
  const k = document.createElement("span");
  k.className = "kv-key";
  k.textContent = label;
  const v = document.createElement("span");
  v.className = valueClass ? `kv-val ${valueClass}` : "kv-val";
  v.textContent = String(value);
  row.appendChild(k);
  row.appendChild(v);
  return row;
}

function renderYourDetailsModalContent(meData) {
  el.yourDetailsModalBody.innerHTML = "";

  if (state.mode === "informatica") {
    const me = meData;
    if (!me) {
      const msg = document.createElement("p");
      msg.style.cssText = "margin:0;color:var(--text-muted);font-size:0.9rem;";
      msg.textContent = "Guest details are temporarily unavailable.";
      el.yourDetailsModalBody.appendChild(msg);
      return;
    }

    const guestSec = document.createElement("section");
    guestSec.className = "details-modal-section";

    const headRow = document.createElement("div");
    headRow.className = "side-card-title-wrap";
    headRow.style.marginBottom = "0.35rem";
    const nameEl = document.createElement("div");
    nameEl.className = "guest-hero-name";
    nameEl.textContent = me.full_name || me.first_name || "Guest";
    headRow.appendChild(nameEl);
    guestSec.appendChild(headRow);

    const kv = document.createElement("div");
    kv.className = "kv-table";
    kv.appendChild(createModalKvRow("Customer ID", me.customer_id || "", "mono"));
    if (me.email) kv.appendChild(createModalKvRow("Email", me.email));
    if (me.phone) kv.appendChild(createModalKvRow("Phone", me.phone));
    guestSec.appendChild(kv);
    el.yourDetailsModalBody.appendChild(guestSec);

    const bookingsSec = document.createElement("section");
    bookingsSec.className = "details-modal-section";
    const bookingsTitle = document.createElement("h3");
    bookingsTitle.className = "details-modal-section-title";
    bookingsTitle.textContent = "Booking Details";
    bookingsSec.appendChild(bookingsTitle);
    bookingsSec.appendChild(buildInfaBookingsFragment(me.bookings));
    el.yourDetailsModalBody.appendChild(bookingsSec);
    return;
  }

  // Mock mode fallback summary inside the modal
  const profile = state.profile || ANONYMOUS_FALLBACK_PROFILE;
  const mockSec = document.createElement("section");
  mockSec.className = "details-modal-section";
  const nameEl = document.createElement("div");
  nameEl.className = "guest-hero-name";
  nameEl.style.marginBottom = "0.5rem";
  nameEl.textContent = profile.guest_status === "anonymous" ? "Anonymous Visitor" : `${profile.first_name} ${profile.last_name}`.trim();
  mockSec.appendChild(nameEl);

  const kv = document.createElement("div");
  kv.className = "kv-table";
  kv.appendChild(createModalKvRow("Customer ID", profile.rcyc_id || "ANONYMOUS", "mono"));
  mockSec.appendChild(kv);
  el.yourDetailsModalBody.appendChild(mockSec);
}

function closeYourDetailsModal() {
  if (el.yourDetailsModal) {
    el.yourDetailsModal.classList.add("hidden");
  }
}

async function openYourDetailsModal() {
  if (!el.yourDetailsModal || !el.yourDetailsModalBody) return;
  el.yourDetailsModal.classList.remove("hidden");

  if (state.mode !== "informatica") {
    renderYourDetailsModalContent(null);
    return;
  }

  if (state.me) {
    renderYourDetailsModalContent(state.me);
  } else {
    el.yourDetailsModalBody.innerHTML =
      '<div class="details-modal-section"><p style="margin:0;color:var(--text-muted);font-size:0.9rem;">Loading your details…</p></div>';
  }

  try {
    const res = await apiFetch("/api/me");
    if (res.status === 401) {
      closeYourDetailsModal();
      clearSessionToken();
      resetRuntimeSessionToLogin();
      return;
    }
    if (!res.ok) {
      if (!state.me) renderYourDetailsModalContent(null);
      return;
    }
    const freshMe = await res.json();
    renderInformaticaMe(freshMe);
    renderYourDetailsModalContent(freshMe);
  } catch (err) {
    if (!state.me) {
      renderYourDetailsModalContent(null);
    }
  }
}

function resetRuntimeSessionToLogin(errorMsg = "") {
  closeYourDetailsModal();
  closeHistoryDrawer();
  state.me = null;
  state.rcycId = "";
  state.conversations = [];
  state.activeConversationId = null;
  state.pendingDeleteConversationId = null;
  state.history = [];
  state.uiMessages = [];
  if (el.historyList) el.historyList.innerHTML = "";
  if (el.chatMessages) el.chatMessages.innerHTML = "";
  showLoginView(errorMsg);
}

async function sendMessage(text) {
  const trimmed = text.trim();
  if (!trimmed || state.busy) return;

  const isFirstUserMessage = !state.uiMessages.some(
    (m) => m && m.role === "user" && m.content && m.content.trim()
  );

  state.busy = true;
  el.sendBtn.disabled = true;
  el.typingIndicator.classList.remove("is-idle");
  el.typingIndicator.setAttribute("aria-hidden", "false");

  appendMessage({ role: "user", content: trimmed });
  el.messageInput.value = "";
  const targetConvId = state.activeConversationId;

  const triggerTitleOnce = () => {
    if (!isFirstUserMessage || !targetConvId) return;
    const targetConv = state.conversations.find((c) => c.id === targetConvId);
    if (!targetConv || targetConv.titleGenerated) return;
    void requestConversationTitle(trimmed).then((generatedTitle) => {
      setConversationTitleOnce(targetConvId, generatedTitle);
    });
  };

  try {
    const bodyPayload =
      state.mode === "informatica"
        ? { message: trimmed, history: state.history }
        : { rcyc_id: state.rcycId, message: trimmed, history: state.history };

    const res = await apiFetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(bodyPayload),
    });

    if (state.mode === "informatica" && res.status === 401) {
      clearSessionToken();
      resetRuntimeSessionToLogin();
      return;
    }
    if (state.mode === "informatica" && res.status === 503) {
      appendMessage({
        role: "assistant",
        content: "Your guest profile service is temporarily unavailable. Your session remains active—please try again in a moment.",
      });
      triggerTitleOnce();
      return;
    }
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    const voyageIds = [
      ...(data.recommendations || []).map((r) => r.voyage.voyage_id),
      ...(data.referenced_voyages || []).map((v) => v.voyage_id),
    ];

    state.history.push({ role: "user", content: trimmed, voyage_ids: [] });
    state.history.push({ role: "assistant", content: data.reply, voyage_ids: voyageIds });

    if (state.mode === "informatica") {
      renderEscalation(data.escalation);
    } else {
      renderProfile(data.guest_profile, data.bookings, data.escalation);
      updateDemoInsights(data);
    }
    appendMessage({
      role: "assistant",
      content: data.reply,
      recommendations: data.recommendations,
      referencedVoyages: data.referenced_voyages,
    });
    triggerTitleOnce();
  } catch (err) {
    appendMessage({
      role: "assistant",
      content: "We apologize—MARIS encountered a brief connection issue. Please try again in a moment.",
    });
    triggerTitleOnce();
  } finally {
    state.busy = false;
    el.sendBtn.disabled = false;
    el.typingIndicator.classList.add("is-idle");
    el.typingIndicator.setAttribute("aria-hidden", "true");
    el.chatMessages.scrollTop = el.chatMessages.scrollHeight;
  }
}

async function openCatalogModal() {
  el.catalogModal.classList.remove("hidden");
  if (state.voyagesLoaded) return;

  try {
    const res = await apiFetch("/api/voyages");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const voyages = await res.json();
    el.catalogGrid.innerHTML = "";

    for (const v of voyages) {
      const card = document.createElement("article");
      card.className = "catalog-card";

      const top = document.createElement("div");
      const kicker = document.createElement("div");
      kicker.style.cssText = "display:flex;justify-content:space-between;font-size:0.74rem;color:var(--text-muted);margin-bottom:0.25rem;";
      const idSpan = document.createElement("span");
      idSpan.className = "mono";
      idSpan.style.cssText = "color:var(--navy-ink);font-weight:600;";
      idSpan.textContent = v.voyage_id;
      const shipSpan = document.createElement("span");
      shipSpan.textContent = v.yacht_name;
      kicker.appendChild(idSpan);
      kicker.appendChild(shipSpan);

      const nameDiv = document.createElement("div");
      nameDiv.style.cssText = "font-size:1.05rem;font-weight:700;color:var(--navy-ink);";
      nameDiv.textContent = v.voyage_name;

      const metaDiv = document.createElement("div");
      metaDiv.style.cssText = "font-size:0.8rem;color:var(--text-muted);margin-top:0.2rem;";
      metaDiv.textContent = `${v.destination} · ${v.duration} nights · ${v.season} · From ${formatCurrency(v.price)}`;

      const hlP = document.createElement("p");
      hlP.style.cssText = "font-size:0.8rem;margin:0.55rem 0 0;color:var(--text);";
      hlP.textContent = v.highlights;

      top.appendChild(kicker);
      top.appendChild(nameDiv);
      top.appendChild(metaDiv);
      top.appendChild(hlP);

      const bottom = document.createElement("div");
      const suitesDiv = document.createElement("div");
      suitesDiv.style.cssText = "font-size:0.75rem;color:var(--text-muted);margin-bottom:0.55rem;";
      suitesDiv.textContent = `Suites: ${v.suite_availability}`;

      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "catalog-card-btn";
      btn.textContent = "Ask MARIS About This Voyage";
      btn.addEventListener("click", () => {
        el.catalogModal.classList.add("hidden");
        sendMessage(`Tell me about ${v.voyage_id} (${v.voyage_name}) and its highlights.`);
      });

      bottom.appendChild(suitesDiv);
      bottom.appendChild(btn);

      card.appendChild(top);
      card.appendChild(bottom);
      el.catalogGrid.appendChild(card);
    }
    state.voyagesLoaded = true;
  } catch (err) {
    el.catalogGrid.textContent = "Voyage collection is temporarily unavailable.";
  }
}

function closePopover() {
  el.accountPopover.classList.add("hidden");
  el.accountMenuBtn.setAttribute("aria-expanded", "false");
}

function toggleDemoInsights(forceState) {
  const shouldOpen =
    typeof forceState === "boolean"
      ? forceState
      : el.demoInsightsDrawer.classList.contains("hidden");
  el.demoInsightsDrawer.classList.toggle("hidden", !shouldOpen);
  el.demoInsightsToggleBtn.setAttribute("aria-expanded", String(shouldOpen));
}

// Header Popover Controls
el.accountMenuBtn.addEventListener("click", (e) => {
  e.stopPropagation();
  const isHidden = el.accountPopover.classList.toggle("hidden");
  el.accountMenuBtn.setAttribute("aria-expanded", String(!isHidden));
});

document.addEventListener("click", (e) => {
  if (!el.accountPopover.contains(e.target) && !el.accountMenuBtn.contains(e.target)) {
    closePopover();
  }
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    closePopover();
    closeYourDetailsModal();
    if (isMobileViewport() && state.sidebarOpen) {
      applySidebarOpenState(false, { persist: true });
    }
    el.catalogModal.classList.add("hidden");
    toggleDemoInsights(false);
  }
});

el.demoInsightsToggleBtn.addEventListener("click", () => toggleDemoInsights());
el.closeDemoInsightsBtn.addEventListener("click", () => toggleDemoInsights(false));

el.popoverMyProfileBtn.addEventListener("click", (e) => {
  e.preventDefault();
  e.stopPropagation();
  closePopover();
  openYourDetailsModal();
});

el.popoverSwitchAnonBtn.addEventListener("click", () => {
  closePopover();
  selectGuest("ANONYMOUS");
});

el.popoverLogoutBtn.addEventListener("click", async (e) => {
  e.preventDefault();
  closePopover();
  clearSavedActiveConversationId();
  try {
    await apiFetch("/api/logout", { method: "POST" });
  } catch (err) {
    // Ignore network error on logout cleanup
  }
  clearSessionToken();
  el.loginPassword.value = "";
  // Keep Customer ID conversations in localStorage on sign out; clear runtime UI state only
  resetRuntimeSessionToLogin();
});

if (el.togglePasswordBtn) {
  el.togglePasswordBtn.addEventListener("click", () => {
    const showing = el.loginPassword.type === "text";
    el.loginPassword.type = showing ? "password" : "text";
    el.togglePasswordBtn.textContent = showing ? "Show" : "Hide";
    el.togglePasswordBtn.setAttribute("aria-label", showing ? "Show password" : "Hide password");
    el.togglePasswordBtn.setAttribute("aria-pressed", String(!showing));
  });
}

el.infaLoginForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const customerId = el.loginCustomerId.value.trim();
  const password = el.loginPassword.value;
  if (!customerId || !password) return;

  el.loginSubmitBtn.disabled = true;
  el.loginSubmitBtn.textContent = "Signing in...";
  el.loginError.classList.add("hidden");

  try {
    const res = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ customer_id: customerId, password }),
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      el.loginError.textContent = body.detail || "Invalid ID or password.";
      el.loginError.classList.remove("hidden");
      return;
    }

    if (body.token) {
      setSessionToken(body.token);
    }
    el.loginPassword.value = "";
    const meRes = await apiFetch("/api/me");
    if (meRes.status === 401) {
      clearSessionToken();
      el.loginError.textContent = "Session expired or invalid. Please sign in again.";
      el.loginError.classList.remove("hidden");
      return;
    }
    if (!meRes.ok) {
      const meErr = await meRes.json().catch(() => ({}));
      el.loginError.textContent = meErr.detail || "Unable to load profile.";
      el.loginError.classList.remove("hidden");
      return;
    }
    const me = await meRes.json();
    hideLoginView();
    renderEscalation(null);
    renderInformaticaMe(me);
    renderInformaticaWelcome(me, { isFreshLogin: true });
  } catch (err) {
    el.loginError.textContent = "Unable to connect to sign-in service.";
    el.loginError.classList.remove("hidden");
  } finally {
    el.loginSubmitBtn.disabled = false;
    el.loginSubmitBtn.textContent = "Sign in";
  }
});

// Guest Selectors & Sample ID Lookup
el.guestSelect.addEventListener("change", (e) => {
  el.inlineRcycInput.value = "";
  closePopover();
  selectGuest(e.target.value);
});

el.inlineGuestSelect.addEventListener("change", (e) => {
  el.inlineRcycInput.value = "";
  selectGuest(e.target.value);
});

el.inlineLookupForm.addEventListener("submit", (e) => {
  e.preventDefault();
  const entered = el.inlineRcycInput.value.trim();
  if (entered) {
    selectGuest(entered);
  }
});

// Mobile collapsible "Your details" (only <=760px; desktop >760px always shows panel)
let lastMobileViewport = isMobileViewport();

function initMobileDetailsState() {
  const mobileNow = isMobileViewport();
  if (mobileNow) {
    el.sidebarPanel.classList.add("is-collapsed-mobile");
    el.mobileDetailsToggle.setAttribute("aria-expanded", "false");
    el.mobileDetailsChevron.style.transform = "rotate(0deg)";
  } else {
    el.sidebarPanel.classList.remove("is-collapsed-mobile");
    el.mobileDetailsToggle.setAttribute("aria-expanded", "true");
  }

  if (mobileNow !== lastMobileViewport) {
    lastMobileViewport = mobileNow;
    applySidebarOpenState(getSavedSidebarOpen(mobileNow), { persist: false });
  } else {
    applySidebarOpenState(state.sidebarOpen, { persist: false });
  }
}

el.mobileDetailsToggle.addEventListener("click", () => {
  const collapsed = el.sidebarPanel.classList.toggle("is-collapsed-mobile");
  el.mobileDetailsToggle.setAttribute("aria-expanded", String(!collapsed));
  el.mobileDetailsChevron.style.transform = collapsed ? "rotate(0deg)" : "rotate(180deg)";
});

window.addEventListener("resize", initMobileDetailsState);

// Chat & Modal Controls
el.chatForm.addEventListener("submit", (e) => {
  e.preventDefault();
  sendMessage(el.messageInput.value);
});

el.toggleContextPacketBtn.addEventListener("click", () => {
  el.escalationPacketPre.classList.toggle("hidden");
});

document.querySelectorAll(".quick-pill").forEach((btn) => {
  btn.addEventListener("click", () => {
    sendMessage(btn.getAttribute("data-prompt") || "");
  });
});

el.catalogTriggerBtn.addEventListener("click", openCatalogModal);
el.closeCatalogBtn.addEventListener("click", () => {
  el.catalogModal.classList.add("hidden");
});
el.catalogModal.addEventListener("click", (e) => {
  if (e.target === el.catalogModal) {
    el.catalogModal.classList.add("hidden");
  }
});

if (el.closeDetailsModalBtn) {
  el.closeDetailsModalBtn.addEventListener("click", closeYourDetailsModal);
}
if (el.yourDetailsModal) {
  el.yourDetailsModal.addEventListener("click", (e) => {
    if (e.target === el.yourDetailsModal) {
      closeYourDetailsModal();
    }
  });
}

if (el.newConversationBtn) {
  el.newConversationBtn.addEventListener("click", () => {
    startNewConversation();
  });
}
if (el.sidebarToggleBtn) {
  el.sidebarToggleBtn.addEventListener("click", () => {
    applySidebarOpenState(!state.sidebarOpen, { persist: true });
  });
}
if (el.closeHistoryDrawerBtn) {
  el.closeHistoryDrawerBtn.addEventListener("click", () => {
    applySidebarOpenState(false, { persist: true });
  });
}
if (el.historyDrawerBackdrop) {
  el.historyDrawerBackdrop.addEventListener("click", () => {
    applySidebarOpenState(false, { persist: true });
  });
}

// Initialize
(async function init() {
  try {
    state.sidebarOpen = getSavedSidebarOpen();
    initMobileDetailsState();
  } catch (err) {
    // Non-fatal UI responsive setup failure
  }

  let dataProvider = "mock";
  try {
    const hRes = await fetch("/api/health");
    if (hRes.ok) {
      const hData = await hRes.json();
      dataProvider = hData.data_provider || "mock";
    }
  } catch (err) {
    // Fallback to mock startup flow if health check fails
  }

  if (dataProvider === "informatica") {
    state.mode = "informatica";
    configureInformaticaChrome();
    try {
      const meRes = await apiFetch("/api/me");
      if (meRes.status === 401) {
        clearSessionToken();
        showLoginView();
        return;
      }
      if (meRes.status === 503) {
        hideLoginView();
        renderInformaticaWelcome(null, { isFreshLogin: false });
        appendMessage({
          role: "assistant",
          content: "Your guest profile service is temporarily unavailable. Your session remains active—please refresh in a moment.",
        });
        return;
      }
      if (!meRes.ok) {
        clearSessionToken();
        showLoginView();
        return;
      }
      const me = await meRes.json();
      hideLoginView();
      renderInformaticaMe(me);
      renderInformaticaWelcome(me, { isFreshLogin: false });
      return;
    } catch (err) {
      showLoginView("Unable to reach guest profile service.");
      return;
    }
  }

  configureMockChrome();
  try {
    const guests = await loadGuestsDropdown();
    const savedGuest = (safeStorageGet(ACTIVE_MOCK_GUEST_KEY) || "").trim().toUpperCase();
    if (guests && savedGuest && state.sampleIds.has(savedGuest)) {
      const ok = await selectGuest(savedGuest);
      if (ok) return;
    }
    if (guests && state.sampleIds.has("RCYC-1001")) {
      const ok = await selectGuest("RCYC-1001");
      if (ok) return;
    }
    await selectGuest("ANONYMOUS");
  } catch (err) {
    syncSelects("ANONYMOUS");
    updateDemoInsights(null);
    renderProfile(ANONYMOUS_FALLBACK_PROFILE, [], null);
    renderWelcomeMessage(ANONYMOUS_FALLBACK_PROFILE);
  }
})();
