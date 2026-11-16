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
const THEME_STORAGE_KEY = "maris_theme:v1";
const MAX_CONVERSATIONS_PER_CUSTOMER = 30;
const MAX_MESSAGES_PER_CONVERSATION = 60;
const MOBILE_BREAKPOINT_PX = 1100;
const FOLLOWUP_CHIPS_IDLE_MS = 8000;

const STARTING_CHIPS = [
  {
    label: "Best voyage for me",
    prompt: "Suggest the best voyage for me.",
    icon: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>',
  },
  {
    label: "Dining options",
    prompt: "Show dining options voyages.",
    icon: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 2v7c0 1.1.9 2 2 2h4a2 2 0 0 0 2-2V2"/><path d="M7 2v20"/><path d="M21 15V2v0a5 5 0 0 0-5 5v6c0 1.1.9 2 2 2h3Zm0 0v7"/></svg>',
  },
  {
    label: "Shore excursions",
    prompt: "Show shore excursions voyages.",
    icon: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76"/></svg>',
  },
  {
    label: "Spa & wellness",
    prompt: "Show spa & wellness voyages.",
    icon: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>',
  },
  {
    label: "Mediterranean",
    prompt: "Show Mediterranean voyages.",
    icon: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>',
  },
  {
    label: "Something different",
    prompt: "Show me something different from my previous voyage.",
    icon: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>',
  },
  {
    label: "Experience Ambassador",
    prompt: "I want to speak with an Experience Ambassador.",
    icon: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="8.5" cy="7" r="4"/><polyline points="17 11 19 13 23 9"/></svg>',
  },
];

const VISITOR_STARTING_CHIPS = [
  {
    label: "Voyage Collection",
    prompt: "Show me the Voyage Collection.",
    icon: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>',
  },
  {
    label: "Mediterranean",
    prompt: "Show Mediterranean voyages.",
    icon: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>',
  },
  {
    label: "Dining options",
    prompt: "Show dining options voyages.",
    icon: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 2v7c0 1.1.9 2 2 2h4a2 2 0 0 0 2-2V2"/><path d="M7 2v20"/><path d="M21 15V2v0a5 5 0 0 0-5 5v6c0 1.1.9 2 2 2h3Zm0 0v7"/></svg>',
  },
  {
    label: "Shore excursions",
    prompt: "Show shore excursions voyages.",
    icon: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76"/></svg>',
  },
  {
    label: "Spa & wellness",
    prompt: "Show spa & wellness voyages.",
    icon: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>',
  },
  {
    label: "Experience Ambassador",
    prompt: "I want to speak with an Experience Ambassador.",
    icon: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="8.5" cy="7" r="4"/><polyline points="17 11 19 13 23 9"/></svg>',
  },
  {
    label: "Sign in for personal help",
    prompt: "Sign in for personal help",
    icon: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/><polyline points="10 17 15 12 10 7"/><line x1="15" y1="12" x2="3" y2="12"/></svg>',
  },
];

const memoryConversationsStore = new Map();

const state = {
  mode: "mock",
  isVisitor: false,
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
  followupIdleTimer: null,
  pendingSuggestedReplies: [],
};

const el = {
  infaLoginView: document.getElementById("infaLoginView"),
  infaLoginForm: document.getElementById("infaLoginForm"),
  loginCustomerId: document.getElementById("loginCustomerId"),
  loginPassword: document.getElementById("loginPassword"),
  togglePasswordBtn: document.getElementById("togglePasswordBtn"),
  loginError: document.getElementById("loginError"),
  loginSubmitBtn: document.getElementById("loginSubmitBtn"),
  continueVisitorBtn: document.getElementById("continueVisitorBtn"),
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
  topbarAccountDivider: document.getElementById("topbarAccountDivider"),
  themeToggleBtn: document.getElementById("themeToggleBtn"),
  themeIconMoon: document.getElementById("themeIconMoon"),
  themeIconSun: document.getElementById("themeIconSun"),
  headerGreeting: document.getElementById("headerGreeting"),
  accountMenuBtn: document.getElementById("accountMenuBtn"),
  accountPopover: document.getElementById("accountPopover"),
  popoverMyProfileBtn: document.getElementById("popoverMyProfileBtn"),
  popoverSwitchAnonBtn: document.getElementById("popoverSwitchAnonBtn"),
  popoverVisitorSignInBtn: document.getElementById("popoverVisitorSignInBtn"),
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
  quickPrompts: document.getElementById("quickPrompts"),
  chatForm: document.getElementById("chatForm"),
  messageInput: document.getElementById("messageInput"),
  sendBtn: document.getElementById("sendBtn"),
  sidebarPanel: document.getElementById("guest-profile-panel"),
  profileKicker: document.getElementById("profileKicker"),
  vipBadge: document.getElementById("vipBadge"),
  guestHeroRow: document.getElementById("guestHeroRow"),
  profileName: document.getElementById("profileName"),
  profileStatusSubtitle: document.getElementById("profileStatusSubtitle"),
  consentOffNotice: document.getElementById("consentOffNotice"),
  demoConsentNotice: document.getElementById("demoConsentNotice"),
  rowCustomerId: document.getElementById("rowCustomerId"),
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
  dataDrawer: document.getElementById("dataDrawer"),
  dataDrawerBackdrop: document.getElementById("dataDrawerBackdrop"),
  closeDataDrawerBtn: document.getElementById("closeDataDrawerBtn"),
  catalogTriggerBtn: document.getElementById("catalogTriggerBtn"),
  closeCatalogBtn: document.getElementById("closeCatalogBtn"),
  catalogModal: document.getElementById("catalogModal"),
  catalogGrid: document.getElementById("catalogGrid"),
};

function getSystemPreferredTheme() {
  try {
    if (typeof window !== "undefined" && window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches) {
      return "dark";
    }
  } catch (err) {
    // Fallback to light theme when matchMedia is unavailable
  }
  return "light";
}

function readSavedThemePreference() {
  try {
    if (typeof window !== "undefined" && window.localStorage) {
      const saved = window.localStorage.getItem(THEME_STORAGE_KEY);
      if (saved === "light" || saved === "dark") {
        return saved;
      }
    }
  } catch (err) {
    // Fall back to system setting when localStorage is unavailable
  }
  return null;
}

function applyTheme(theme, { persist = false } = {}) {
  const normalized = theme === "dark" ? "dark" : "light";
  if (typeof document !== "undefined" && document.documentElement) {
    document.documentElement.setAttribute("data-theme", normalized);
    document.documentElement.style.colorScheme = normalized;
  }
  if (el.themeToggleBtn) {
    const label = normalized === "dark" ? "Switch to light mode" : "Switch to dark mode";
    el.themeToggleBtn.setAttribute("aria-label", label);
    el.themeToggleBtn.setAttribute("title", label);
  }
  if (el.themeIconMoon && el.themeIconSun) {
    el.themeIconMoon.classList.toggle("hidden", normalized === "dark");
    el.themeIconSun.classList.toggle("hidden", normalized !== "dark");
  }
  if (persist) {
    try {
      if (typeof window !== "undefined" && window.localStorage) {
        window.localStorage.setItem(THEME_STORAGE_KEY, normalized);
      }
    } catch (err) {
      // Ignore storage write failure; in-memory document theme still applies
    }
  }
}

function getCurrentTheme() {
  if (typeof document !== "undefined" && document.documentElement) {
    return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
  }
  return "light";
}

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
  if (state.isVisitor) return null;
  const key = getActiveConversationStorageKey(sessionIdOverride);
  if (!key) return null;
  const val = safeStorageGet(key);
  return val && val.trim() ? val.trim() : null;
}

function setSavedActiveConversationId(conversationId, sessionIdOverride = null) {
  if (state.isVisitor) return;
  const key = getActiveConversationStorageKey(sessionIdOverride);
  if (!key) return;
  if (conversationId) {
    safeStorageSet(key, String(conversationId));
  } else {
    safeStorageRemove(key);
  }
}

function clearSavedActiveConversationId(sessionIdOverride = null) {
  if (state.isVisitor) return;
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
      suggestedReplies: Array.isArray(m.suggestedReplies) ? m.suggestedReplies.map(String).slice(0, 3) : [],
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
  if (state.isVisitor) return;
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
  if (state.isVisitor) return [];
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
  if (state.isVisitor) return;
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

    selectBtn.appendChild(titleEl);
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
  if (state.isVisitor) {
    return (
      "Hello and welcome to **MARIS**, your personal yacht concierge for The Ritz-Carlton Yacht Collection. " +
      "I can help you explore our voyage collection, destinations, suites, dining, spa & wellness, and shore excursions—" +
      "or sign in anytime for bookings and personalized assistance."
    );
  }
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

function hasSentUserMessage() {
  return state.uiMessages.some((m) => m && m.role === "user" && m.content && m.content.trim());
}

function clearFollowupIdleTimer() {
  if (state.followupIdleTimer !== null) {
    clearTimeout(state.followupIdleTimer);
    state.followupIdleTimer = null;
  }
}

function renderPromptChips(items, { isStarting = false } = {}) {
  if (!el.quickPrompts) return;
  el.quickPrompts.innerHTML = "";
  for (const item of items) {
    const label = isStarting ? item.label : String(item || "").trim();
    const promptText = isStarting ? item.prompt : label;
    if (!label || !promptText) continue;

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "quick-pill";
    btn.setAttribute("data-prompt", promptText);
    if (isStarting && item.icon) {
      btn.innerHTML = item.icon;
    }
    const span = document.createElement("span");
    span.textContent = label;
    btn.appendChild(span);
    btn.addEventListener("click", () => {
      sendMessage(promptText);
    });
    el.quickPrompts.appendChild(btn);
  }
}

function setChipsVisible(visible) {
  if (!el.quickPrompts) return;
  el.quickPrompts.classList.toggle("is-chips-hidden", !visible);
  el.quickPrompts.setAttribute("aria-hidden", String(!visible));
  el.quickPrompts.querySelectorAll("button").forEach((btn) => {
    btn.tabIndex = visible ? 0 : -1;
    btn.disabled = !visible;
  });
}

function hideChips({ clearPending = false } = {}) {
  clearFollowupIdleTimer();
  if (clearPending) {
    state.pendingSuggestedReplies = [];
  }
  setChipsVisible(false);
}

function showStartingChips() {
  clearFollowupIdleTimer();
  state.pendingSuggestedReplies = [];
  const chips = state.isVisitor ? VISITOR_STARTING_CHIPS : STARTING_CHIPS;
  renderPromptChips(chips, { isStarting: true });
  setChipsVisible(true);
}

function scheduleFollowupChips(replies) {
  clearFollowupIdleTimer();
  const list = Array.isArray(replies)
    ? replies.map((s) => String(s || "").trim()).filter(Boolean).slice(0, 3)
    : [];
  state.pendingSuggestedReplies = list;
  setChipsVisible(false);
  if (list.length === 0 || state.busy) {
    return;
  }
  state.followupIdleTimer = setTimeout(() => {
    state.followupIdleTimer = null;
    if (state.busy || !hasSentUserMessage()) return;
    if (el.messageInput && el.messageInput.value.trim() !== "") return;
    if (!Array.isArray(state.pendingSuggestedReplies) || state.pendingSuggestedReplies.length === 0) return;
    renderPromptChips(state.pendingSuggestedReplies, { isStarting: false });
    if (el.quickPrompts) {
      void el.quickPrompts.offsetWidth;
    }
    setChipsVisible(true);
  }, FOLLOWUP_CHIPS_IDLE_MS);
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
    suggestedReplies: [],
    timestamp: currentTimeStr(),
  };
  state.uiMessages.push(welcomeMsg);
  appendMessage(welcomeMsg, { persist: false });
  showStartingChips();
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
  if (!hasSentUserMessage()) {
    showStartingChips();
  } else {
    const lastAssistant = [...state.uiMessages].reverse().find((m) => m.role === "assistant");
    scheduleFollowupChips(lastAssistant ? lastAssistant.suggestedReplies : []);
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
      <path d="M18 5L29 24H18V5Z" fill="var(--gold)"/>
      <path d="M16 9L8 24H16V9Z" fill="var(--gold)" fill-opacity="0.82"/>
      <path d="M5 26.5H31L27.5 30.5H8.5L5 26.5Z" fill="var(--gold)"/>
    </svg>
  `;
  return wrap;
}

function appendMessage(
  { role, content, recommendations = [], referencedVoyages = [], suggestedReplies = [], timestamp = null },
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
            <path d="M18 6L28 24H18V6Z" fill="var(--sail-primary)"/>
            <path d="M16 10L9 24H16V10Z" fill="var(--sail-secondary)"/>
            <path d="M6 26H30L27 29.5H9L6 26Z" fill="var(--sail-primary)"/>
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
      suggestedReplies: Array.isArray(suggestedReplies) ? suggestedReplies.map(String).slice(0, 3) : [],
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
  state.isVisitor = false;
  if (el.workspaceMain) el.workspaceMain.classList.remove("is-visitor-mode");
  el.chatIdentityStrip.classList.remove("hidden");
  el.guestPickerSection.classList.remove("hidden");
  el.guestPickerDivider.classList.remove("hidden");
  el.popoverMyProfileBtn.classList.remove("hidden");
  el.popoverSwitchAnonBtn.classList.remove("hidden");
  if (el.popoverVisitorSignInBtn) el.popoverVisitorSignInBtn.classList.add("hidden");
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
  state.isVisitor = false;
  if (el.workspaceMain) el.workspaceMain.classList.remove("is-visitor-mode");
  el.chatIdentityStrip.classList.add("hidden");
  el.guestPickerSection.classList.add("hidden");
  el.guestPickerDivider.classList.add("hidden");
  el.popoverMyProfileBtn.classList.remove("hidden");
  el.popoverSwitchAnonBtn.classList.add("hidden");
  if (el.popoverVisitorSignInBtn) el.popoverVisitorSignInBtn.classList.add("hidden");
  el.popoverLogoutBtn.classList.remove("hidden");
  el.demoInsightsToggleBtn.classList.add("hidden");
  el.demoInsightsDrawer.classList.add("hidden");
  el.demoFooter.classList.add("hidden");
}

function configureVisitorChrome() {
  state.isVisitor = true;
  state.me = null;
  state.rcycId = "";
  state.bookings = [];
  if (el.workspaceMain) {
    el.workspaceMain.classList.add("is-visitor-mode");
    el.workspaceMain.classList.remove("is-sidebar-collapsed");
  }
  if (el.sidebarToggleBtn) el.sidebarToggleBtn.classList.add("hidden");
  if (el.historySidebar) el.historySidebar.classList.remove("is-open-mobile");
  if (el.historyDrawerBackdrop) el.historyDrawerBackdrop.classList.add("hidden");
  el.chatIdentityStrip.classList.add("hidden");
  el.guestPickerSection.classList.add("hidden");
  el.guestPickerDivider.classList.add("hidden");
  el.popoverMyProfileBtn.classList.add("hidden");
  el.popoverSwitchAnonBtn.classList.add("hidden");
  el.popoverLogoutBtn.classList.add("hidden");
  if (el.popoverVisitorSignInBtn) el.popoverVisitorSignInBtn.classList.remove("hidden");
  el.demoInsightsToggleBtn.classList.add("hidden");
  el.demoInsightsDrawer.classList.add("hidden");
  el.demoFooter.classList.add("hidden");
  el.headerGreeting.textContent = "Welcome, Guest";
  closeDataDrawer();
}

function enterVisitorMode() {
  clearFollowupIdleTimer();
  state.pendingSuggestedReplies = [];
  state.conversations = [];
  state.activeConversationId = null;
  state.pendingDeleteConversationId = null;
  state.history = [];
  state.uiMessages = [];
  state.isVisitor = true;
  hideLoginView();
  configureVisitorChrome();
  renderEscalation(null);
  startNewConversation();
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
  state.isVisitor = false;
  if (el.workspaceMain) el.workspaceMain.classList.remove("is-visitor-mode");
  el.infaLoginView.classList.remove("hidden");
  el.workspaceMain.classList.add("hidden");
  if (el.sidebarToggleBtn) el.sidebarToggleBtn.classList.add("hidden");
  if (el.topbarAccountDivider) el.topbarAccountDivider.classList.add("hidden");
  el.accountMenuBtn.classList.add("hidden");
  el.catalogTriggerBtn.classList.add("hidden");
  el.demoInsightsToggleBtn.classList.add("hidden");
  el.demoInsightsDrawer.classList.add("hidden");
  el.demoFooter.classList.add("hidden");
  closeDataDrawer();
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
  if (el.sidebarToggleBtn) {
    el.sidebarToggleBtn.classList.toggle("hidden", state.isVisitor);
  }
  if (el.topbarAccountDivider) el.topbarAccountDivider.classList.remove("hidden");
  el.accountMenuBtn.classList.remove("hidden");
  el.catalogTriggerBtn.classList.remove("hidden");
  el.loginError.classList.add("hidden");
  if (!state.isVisitor) {
    applySidebarOpenState(getSavedSidebarOpen(), { persist: false });
  }
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

  const displayName = me.full_name || me.first_name || "";
  if (displayName) {
    el.profileName.textContent = displayName;
    el.profileName.classList.remove("hidden");
  } else {
    el.profileName.textContent = "";
    el.profileName.classList.add("hidden");
  }

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

  if (el.guestHeroRow) {
    el.guestHeroRow.classList.toggle("hidden", !displayName && !me.loyalty_tier);
  }

  el.vipBadge.classList.toggle("hidden", me.vip_status !== true);
  el.consentOffNotice.classList.add("hidden");
  el.demoConsentNotice.classList.add("hidden");

  el.profileIdLabel.textContent = "Customer ID";
  if (me.customer_id) {
    if (el.rowCustomerId) el.rowCustomerId.classList.remove("hidden");
    el.profileRcycId.textContent = me.customer_id;
  } else {
    if (el.rowCustomerId) el.rowCustomerId.classList.add("hidden");
    el.profileRcycId.textContent = "";
  }

  el.rowInfaEmail.classList.remove("hidden");
  if (me.email) {
    el.attrInfaEmail.textContent = me.email;
    el.attrInfaEmail.classList.remove("is-muted");
  } else {
    el.attrInfaEmail.textContent = "Not on file";
    el.attrInfaEmail.classList.add("is-muted");
  }

  el.rowInfaPhone.classList.remove("hidden");
  if (me.phone) {
    el.attrInfaPhone.textContent = me.phone;
    el.attrInfaPhone.classList.remove("is-muted");
  } else {
    el.attrInfaPhone.textContent = "Not on file";
    el.attrInfaPhone.classList.add("is-muted");
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

async function openYourDetailsDrawer() {
  if (state.isVisitor) return;
  openDataDrawer();
  if (state.mode !== "informatica") {
    return;
  }

  try {
    const res = await apiFetch("/api/me");
    if (res.status === 401) {
      closeDataDrawer();
      clearSessionToken();
      resetRuntimeSessionToLogin();
      return;
    }
    if (!res.ok) return;
    const freshMe = await res.json();
    renderInformaticaMe(freshMe);
  } catch (err) {
    // Keep last rendered profile in drawer when refresh fails transiently
  }
}

function resetRuntimeSessionToLogin(errorMsg = "") {
  clearFollowupIdleTimer();
  state.pendingSuggestedReplies = [];
  state.isVisitor = false;
  closeDataDrawer();
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

  const isFirstUserMessage = !hasSentUserMessage();

  state.busy = true;
  el.sendBtn.disabled = true;
  el.typingIndicator.classList.remove("is-idle");
  el.typingIndicator.setAttribute("aria-hidden", "false");
  hideChips({ clearPending: true });

  appendMessage({ role: "user", content: trimmed });
  el.messageInput.value = "";
  const targetConvId = state.activeConversationId;

  const triggerTitleOnce = () => {
    if (state.isVisitor || !isFirstUserMessage || !targetConvId) return;
    const targetConv = state.conversations.find((c) => c.id === targetConvId);
    if (!targetConv || targetConv.titleGenerated) return;
    void requestConversationTitle(trimmed).then((generatedTitle) => {
      setConversationTitleOnce(targetConvId, generatedTitle);
    });
  };

  let nextSuggestedReplies = [];

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
    if (state.isVisitor && res.status === 429) {
      const rateErr = await res.json().catch(() => ({}));
      appendMessage({
        role: "assistant",
        content:
          rateErr.detail ||
          "You have reached the visitor chat limit of 20 messages per 10 minutes. Please wait a few minutes, or sign in for continued assistance from MARIS.",
      });
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

    nextSuggestedReplies = Array.isArray(data.suggested_replies)
      ? data.suggested_replies.slice(0, 3)
      : [];

    appendMessage({
      role: "assistant",
      content: data.reply,
      recommendations: data.recommendations,
      referencedVoyages: data.referenced_voyages,
      suggestedReplies: nextSuggestedReplies,
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
    scheduleFollowupChips(nextSuggestedReplies);
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
      kicker.className = "catalog-card-kicker";
      const idSpan = document.createElement("span");
      idSpan.className = "mono catalog-card-id";
      idSpan.textContent = v.voyage_id;
      const shipSpan = document.createElement("span");
      shipSpan.textContent = v.yacht_name;
      kicker.appendChild(idSpan);
      kicker.appendChild(shipSpan);

      const nameDiv = document.createElement("div");
      nameDiv.className = "catalog-card-title";
      nameDiv.textContent = v.voyage_name;

      const metaDiv = document.createElement("div");
      metaDiv.className = "catalog-card-meta";
      metaDiv.textContent = `${v.destination} · ${v.duration} nights · ${v.season} · From ${formatCurrency(v.price)}`;

      const hlP = document.createElement("p");
      hlP.className = "catalog-card-desc";
      hlP.textContent = v.highlights;

      top.appendChild(kicker);
      top.appendChild(nameDiv);
      top.appendChild(metaDiv);
      top.appendChild(hlP);

      const bottom = document.createElement("div");
      const suitesDiv = document.createElement("div");
      suitesDiv.className = "catalog-card-suites";
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

function openDataDrawer() {
  if (el.dataDrawer) {
    el.dataDrawer.classList.remove("hidden");
  }
  if (el.dataDrawerBackdrop) {
    el.dataDrawerBackdrop.classList.remove("hidden");
  }
  if (el.sidebarPanel) {
    el.sidebarPanel.classList.remove("is-collapsed-mobile");
  }
}

function closeDataDrawer() {
  if (el.dataDrawer) {
    el.dataDrawer.classList.add("hidden");
  }
  if (el.dataDrawerBackdrop) {
    el.dataDrawerBackdrop.classList.add("hidden");
  }
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
    closeDataDrawer();
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
  openYourDetailsDrawer();
});

if (el.closeDataDrawerBtn) {
  el.closeDataDrawerBtn.addEventListener("click", closeDataDrawer);
}

if (el.dataDrawerBackdrop) {
  el.dataDrawerBackdrop.addEventListener("click", closeDataDrawer);
}

el.popoverSwitchAnonBtn.addEventListener("click", () => {
  closePopover();
  selectGuest("ANONYMOUS");
});

if (el.popoverVisitorSignInBtn) {
  el.popoverVisitorSignInBtn.addEventListener("click", async (e) => {
    e.preventDefault();
    closePopover();
    try {
      await apiFetch("/api/logout", { method: "POST" });
    } catch (err) {
      // Ignore network error on visitor sign-in transition
    }
    clearSessionToken();
    el.loginPassword.value = "";
    resetRuntimeSessionToLogin();
  });
}

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
  // Keep Customer ID conversations & user theme preference in localStorage on sign out
  resetRuntimeSessionToLogin();
});

if (el.continueVisitorBtn) {
  el.continueVisitorBtn.addEventListener("click", async () => {
    if (el.continueVisitorBtn.disabled) return;
    el.continueVisitorBtn.disabled = true;
    if (el.loginSubmitBtn) el.loginSubmitBtn.disabled = true;
    el.loginError.classList.add("hidden");

    try {
      const res = await fetch("/api/visitor", {
        method: "POST",
        credentials: "same-origin",
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok || body.role !== "visitor") {
        el.loginError.textContent = body.detail || "Unable to start guest browsing right now.";
        el.loginError.classList.remove("hidden");
        return;
      }
      if (body.token) {
        setSessionToken(body.token);
      }
      enterVisitorMode();
    } catch (err) {
      el.loginError.textContent = "Unable to connect to guest browsing service.";
      el.loginError.classList.remove("hidden");
    } finally {
      el.continueVisitorBtn.disabled = false;
      if (el.loginSubmitBtn) el.loginSubmitBtn.disabled = false;
    }
  });
}

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
  if (el.continueVisitorBtn) el.continueVisitorBtn.disabled = true;
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
    configureInformaticaChrome();
    hideLoginView();
    renderEscalation(null);
    renderInformaticaMe(me);
    renderInformaticaWelcome(me, { isFreshLogin: true });
  } catch (err) {
    el.loginError.textContent = "Unable to connect to sign-in service.";
    el.loginError.classList.remove("hidden");
  } finally {
    el.loginSubmitBtn.disabled = false;
    if (el.continueVisitorBtn) el.continueVisitorBtn.disabled = false;
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

// Theme Toggle & System Preference Sync
if (el.themeToggleBtn) {
  el.themeToggleBtn.addEventListener("click", () => {
    const nextTheme = getCurrentTheme() === "dark" ? "light" : "dark";
    applyTheme(nextTheme, { persist: true });
  });
}

try {
  if (typeof window !== "undefined" && window.matchMedia) {
    const colorSchemeQuery = window.matchMedia("(prefers-color-scheme: dark)");
    const handleSystemThemeChange = (ev) => {
      if (readSavedThemePreference() === null) {
        applyTheme(ev.matches ? "dark" : "light", { persist: false });
      }
    };
    if (typeof colorSchemeQuery.addEventListener === "function") {
      colorSchemeQuery.addEventListener("change", handleSystemThemeChange);
    } else if (typeof colorSchemeQuery.addListener === "function") {
      colorSchemeQuery.addListener(handleSystemThemeChange);
    }
  }
} catch (err) {
  // Ignore matchMedia listener errors
}

// Responsive sidebar state
let lastMobileViewport = isMobileViewport();

function initMobileDetailsState() {
  const mobileNow = isMobileViewport();
  if (el.sidebarPanel) {
    el.sidebarPanel.classList.remove("is-collapsed-mobile");
  }
  if (state.isVisitor) {
    applySidebarOpenState(false, { persist: false });
    return;
  }

  if (mobileNow !== lastMobileViewport) {
    lastMobileViewport = mobileNow;
    applySidebarOpenState(getSavedSidebarOpen(mobileNow), { persist: false });
  } else {
    applySidebarOpenState(state.sidebarOpen, { persist: false });
  }
}

window.addEventListener("resize", initMobileDetailsState);

// Chat & Modal Controls
el.chatForm.addEventListener("submit", (e) => {
  e.preventDefault();
  sendMessage(el.messageInput.value);
});

if (el.messageInput) {
  el.messageInput.addEventListener("input", () => {
    if (!hasSentUserMessage()) return;
    hideChips({ clearPending: false });
    if (el.messageInput.value.trim() === "" && !state.busy && state.pendingSuggestedReplies.length > 0) {
      scheduleFollowupChips(state.pendingSuggestedReplies);
    }
  });
}

el.toggleContextPacketBtn.addEventListener("click", () => {
  el.escalationPacketPre.classList.toggle("hidden");
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

if (el.newConversationBtn) {
  el.newConversationBtn.addEventListener("click", () => {
    startNewConversation();
  });
}
if (el.sidebarToggleBtn) {
  el.sidebarToggleBtn.addEventListener("click", () => {
    if (state.isVisitor) return;
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
    const initialTheme = readSavedThemePreference() || getSystemPreferredTheme();
    applyTheme(initialTheme, { persist: false });
  } catch (err) {
    // Non-fatal theme sync setup failure
  }

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
      const sessRes = await apiFetch("/api/session");
      if (sessRes.ok) {
        const sess = await sessRes.json().catch(() => ({}));
        if (sess.role === "visitor") {
          enterVisitorMode();
          return;
        }
        if (sess.role !== "guest") {
          clearSessionToken();
          showLoginView();
          return;
        }
      }

      const meRes = await apiFetch("/api/me");
      if (meRes.status === 401 || meRes.status === 403) {
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
