import { useEffect, useMemo, useRef, useState } from "react";
import {
  Bot,
  ChevronDown,
  CirclePlus,
  LoaderCircle,
  PanelLeftClose,
  PanelLeftOpen,
  PencilLine,
  Search,
  SendHorizontal,
  Sparkles,
  Trash2,
} from "lucide-react";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";
const ACTIVE_SESSION_STORAGE_KEY = "fakeguard-active-session-id";
const HISTORY_FILTER_STORAGE_KEY = "fakeguard-history-filter";

const SPORT_OPTIONS = [
  { value: "bong_da", label: "Bóng đá", icon: "⚽" },
  { value: "bong_ro", label: "Bóng rổ", icon: "🏀" },
  { value: "tennis", label: "Tennis", icon: "🎾" },
  { value: "bong_chay", label: "Bóng chày", icon: "⚾" },
];

const HISTORY_FILTERS = [{ value: "all", label: "Tất cả", icon: "◌" }, ...SPORT_OPTIONS];

const THINKING_STEPS = [
  "Phân tích claim và nhận diện thực thể chính",
  "Tra cứu dữ liệu nội bộ",
  "Mở rộng kiểm tra nguồn web khi cần",
  "Đối chiếu bằng chứng hỗ trợ và bác bỏ",
  "Tổng hợp kết luận cuối cùng",
];

const starterMessages = [
  {
    id: "assistant-welcome",
    role: "assistant",
    type: "welcome",
    content: "Nhập một đoạn tin hoặc claim thể thao. Tôi sẽ kiểm tra bằng dữ liệu nội bộ và web khi cần.",
    timestamp: timeLabel(),
  },
];

function timeLabel(value) {
  const date = value ? new Date(value) : new Date();
  return date.toLocaleTimeString("vi-VN", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function verdictTone(verdict) {
  switch (verdict) {
    case "SUPPORTED":
      return "supported";
    case "REFUTED":
      return "refuted";
    case "NEI":
      return "nei";
    default:
      return "neutral";
  }
}

function formatPercent(value) {
  if (typeof value !== "number" || Number.isNaN(value)) return "--";
  return `${Math.round(value * 100)}%`;
}

function deriveVerdict(payload) {
  if (payload?.verdict) return payload.verdict;

  const claims = payload?.claims ?? [];
  const claimVerdicts = claims.map((item) => item?.verdict).filter(Boolean);

  if (claimVerdicts.includes("REFUTED")) return "REFUTED";
  if (claimVerdicts.includes("SUPPORTED")) return "SUPPORTED";
  if (claimVerdicts.includes("NEI")) return "NEI";
  return "UNKNOWN";
}

function getSportOption(value) {
  return SPORT_OPTIONS.find((item) => item.value === value) || null;
}

function sessionSportLabel(value) {
  const matched = getSportOption(value);
  return matched?.label || "Chung";
}

function sessionSportIcon(value) {
  const matched = getSportOption(value);
  return matched?.icon || "◌";
}

function formatCategoryLabel(value) {
  if (!value) return "--";

  const normalized = String(value).trim().toLowerCase().replace(/-/g, "_").replace(/\s+/g, "_");
  const aliases = {
    football: "bong_da",
    soccer: "bong_da",
    basketball: "bong_ro",
    baseball: "bong_chay",
  };
  const resolved = aliases[normalized] || normalized;
  const matched = getSportOption(resolved);
  return matched?.label || value;
}

function sessionPreview(session) {
  return session.last_message_preview || "Chưa có nội dung.";
}

function buildAssistantMessage(payload, meta = {}) {
  const resolvedVerdict = deriveVerdict(payload);
  return {
    id: payload.message_id || `assistant-${Date.now()}`,
    role: "assistant",
    type: "result",
    timestamp: timeLabel(),
    verdict: resolvedVerdict,
    confidence: payload.confidence,
    explanation: payload.explanation,
    summary: payload.summary,
    category: payload.category,
    claims: payload.claims ?? [],
    sources: payload.sources ?? [],
    thinkingDurationSeconds: meta.thinkingDurationSeconds ?? null,
    thinkingSteps: meta.thinkingSteps ?? [],
  };
}

function buildErrorMessage(message) {
  return {
    id: `assistant-error-${Date.now()}`,
    role: "assistant",
    type: "error",
    timestamp: timeLabel(),
    content: message,
  };
}

function buildUserMessage(text, timestamp) {
  return {
    id: `user-${Date.now()}`,
    role: "user",
    type: "text",
    content: text,
    timestamp: timeLabel(timestamp),
  };
}

function mapApiMessageToUi(message) {
  if (message.role === "user") {
    return {
      ...buildUserMessage(message.content, message.created_at),
      id: message.id,
    };
  }

  if (message.role === "assistant" && message.message_type === "result" && message.payload_json) {
    return {
      ...buildAssistantMessage(message.payload_json),
      id: message.id,
      timestamp: timeLabel(message.created_at),
    };
  }

  return {
    id: message.id,
    role: "assistant",
    type: message.message_type === "error" ? "error" : "welcome",
    content: message.content,
    timestamp: timeLabel(message.created_at),
  };
}

function App() {
  const [messages, setMessages] = useState(starterMessages);
  const [sessions, setSessions] = useState([]);
  const [activeSessionId, setActiveSessionId] = useState(() => localStorage.getItem(ACTIVE_SESSION_STORAGE_KEY));
  const [selectedSportCategory, setSelectedSportCategory] = useState(null);
  const [historyFilter, setHistoryFilter] = useState(() => localStorage.getItem(HISTORY_FILTER_STORAGE_KEY) || "all");
  const [searchQuery, setSearchQuery] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [input, setInput] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [loadingSessions, setLoadingSessions] = useState(false);
  const [loadingConversation, setLoadingConversation] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [historyFilterOpen, setHistoryFilterOpen] = useState(false);
  const [thinkingElapsedSeconds, setThinkingElapsedSeconds] = useState(0);
  const [thinkingStepIndex, setThinkingStepIndex] = useState(0);
  const endRef = useRef(null);
  const historyFilterRef = useRef(null);
  const sportPickerRef = useRef(null);
  const thinkingStepIndexRef = useRef(0);

  const canSubmit = input.trim().length > 0 && !submitting;
  const isEmptyState = messages.length === 1 && messages[0]?.type === "welcome" && !activeSessionId;
  const orderedMessages = useMemo(() => messages, [messages]);
  const activeHistoryFilter = useMemo(
    () => HISTORY_FILTERS.find((item) => item.value === historyFilter) || HISTORY_FILTERS[0],
    [historyFilter],
  );

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      void initializeSidebar(historyFilter, searchQuery);
    }, searchQuery ? 220 : 0);

    return () => window.clearTimeout(timeoutId);
  }, [historyFilter, searchQuery]);

  useEffect(() => {
    if (activeSessionId) {
      localStorage.setItem(ACTIVE_SESSION_STORAGE_KEY, activeSessionId);
    } else {
      localStorage.removeItem(ACTIVE_SESSION_STORAGE_KEY);
    }
  }, [activeSessionId]);

  useEffect(() => {
    localStorage.setItem(HISTORY_FILTER_STORAGE_KEY, historyFilter);
  }, [historyFilter]);

  useEffect(() => {
    queueMicrotask(() => {
      endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    });
  }, [messages, submitting]);

  useEffect(() => {
    thinkingStepIndexRef.current = thinkingStepIndex;
  }, [thinkingStepIndex]);

  useEffect(() => {
    function handleOutsideClick(event) {
      if (!historyFilterRef.current?.contains(event.target)) {
        setHistoryFilterOpen(false);
      }

      if (sportPickerRef.current && !sportPickerRef.current.contains(event.target)) {
        setSelectedSportCategory(null);
      }
    }

    document.addEventListener("mousedown", handleOutsideClick);
    return () => {
      document.removeEventListener("mousedown", handleOutsideClick);
    };
  }, []);

  useEffect(() => {
    if (!submitting) {
      return undefined;
    }

    const elapsedInterval = window.setInterval(() => {
      setThinkingElapsedSeconds((current) => current + 1);
    }, 1000);

    const stepInterval = window.setInterval(() => {
      setThinkingStepIndex((current) => Math.min(current + 1, THINKING_STEPS.length - 1));
    }, 1700);

    return () => {
      window.clearInterval(elapsedInterval);
      window.clearInterval(stepInterval);
    };
  }, [submitting]);

  async function initializeSidebar(filterValue, queryValue = "") {
    setLoadingSessions(true);
    try {
      const params = new URLSearchParams();
      if (filterValue && filterValue !== "all") {
        params.set("sport_category", filterValue);
      }
      if (queryValue.trim()) {
        params.set("q", queryValue.trim());
      }

      const suffix = params.toString() ? `?${params.toString()}` : "";
      const response = await fetch(`${API_BASE_URL}/api/chat/sessions${suffix}`);
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || "Không tải được lịch sử chat.");
      }

      const items = payload.items ?? [];
      setSessions(items);

      if (items.length > 0) {
        const hasActiveInResults = activeSessionId && items.some((item) => item.id === activeSessionId);

        if (hasActiveInResults) {
          await loadSession(activeSessionId);
        } else if (!queryValue.trim()) {
          await loadSession(items[0].id);
        }
      } else {
        setSessions([]);
        if (!queryValue.trim()) {
          setActiveSessionId(null);
          setMessages(starterMessages);
        }
      }
    } catch (error) {
      console.error(error);
    } finally {
      setLoadingSessions(false);
    }
  }

  async function refreshSessions(preferredSessionId = null) {
    const params = new URLSearchParams();
    if (historyFilter !== "all") {
      params.set("sport_category", historyFilter);
    }
    if (searchQuery.trim()) {
      params.set("q", searchQuery.trim());
    }

    const suffix = params.toString() ? `?${params.toString()}` : "";
    const response = await fetch(`${API_BASE_URL}/api/chat/sessions${suffix}`);
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "Không tải được lịch sử chat.");
    }

    const items = payload.items ?? [];
    setSessions(items);

    if (preferredSessionId && items.some((item) => item.id === preferredSessionId)) {
      setActiveSessionId(preferredSessionId);
    } else if (items.length === 0) {
      setActiveSessionId(null);
    }
  }

  async function loadSession(sessionId) {
    if (!sessionId) return;

    setLoadingConversation(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/chat/sessions/${sessionId}`);
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || "Không tải được nội dung cuộc trò chuyện.");
      }

      const nextMessages = (payload.messages ?? []).map(mapApiMessageToUi);
      setActiveSessionId(sessionId);
      if (payload.session?.sport_category && payload.session.sport_category !== "unknown") {
        setSelectedSportCategory(payload.session.sport_category);
      }
      setMessages(nextMessages.length > 0 ? nextMessages : starterMessages);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Không tải được lịch sử hội thoại.";
      setMessages([buildErrorMessage(message)]);
    } finally {
      setLoadingConversation(false);
    }
  }

  async function handleDeleteSession(event, sessionId) {
    event.stopPropagation();
    if (!window.confirm("Xóa cuộc trò chuyện này?")) {
      return;
    }

    try {
      const response = await fetch(`${API_BASE_URL}/api/chat/sessions/${sessionId}`, {
        method: "DELETE",
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || "Không thể xóa cuộc trò chuyện.");
      }

      const nextSessions = sessions.filter((item) => item.id !== sessionId);
      setSessions(nextSessions);

      if (activeSessionId === sessionId) {
        if (nextSessions.length > 0) {
          await loadSession(nextSessions[0].id);
        } else {
          setActiveSessionId(null);
          setMessages(starterMessages);
        }
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "Không thể xóa cuộc trò chuyện.";
      setMessages((current) => [...current, buildErrorMessage(message)]);
    }
  }

  function handleNewChat() {
    setInput("");
    setSelectedSportCategory(null);
    setActiveSessionId(null);
    setMessages(starterMessages);
  }

  function toggleSearchPanel() {
    setSearchOpen((current) => {
      if (current) {
        setSearchQuery("");
      }
      return !current;
    });
  }

  async function handleSubmit(event) {
    event.preventDefault();
    const text = input.trim();
    if (!text || submitting) return;

    const submitStartedAt = Date.now();
    const userMessage = buildUserMessage(text);
    setMessages((current) => (isEmptyState ? [userMessage] : [...current, userMessage]));
    setInput("");
    setThinkingElapsedSeconds(0);
    setThinkingStepIndex(0);
    thinkingStepIndexRef.current = 0;
    setSubmitting(true);

    try {
      const response = await fetch(`${API_BASE_URL}/api/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          session_id: activeSessionId,
          text,
          sport_category: selectedSportCategory,
        }),
      });

      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || "Không thể xử lý yêu cầu.");
      }

      setActiveSessionId(payload.session_id);
      if (payload.sport_category && payload.sport_category !== "unknown") {
        setSelectedSportCategory(payload.sport_category);
        if (historyFilter !== "all" && historyFilter !== payload.sport_category) {
          setHistoryFilter(payload.sport_category);
        }
      }

      const durationSeconds = Math.max(1, Math.round((Date.now() - submitStartedAt) / 1000));
      const completedSteps = THINKING_STEPS.slice(
        0,
        Math.min(thinkingStepIndexRef.current + 1, THINKING_STEPS.length),
      );

      setMessages((current) => [
        ...current,
        buildAssistantMessage(payload, {
          thinkingDurationSeconds: durationSeconds,
          thinkingSteps: completedSteps,
        }),
      ]);
      await refreshSessions(payload.session_id);
    } catch (error) {
      const message =
        error instanceof Error && error.message === "Failed to fetch"
          ? "Không kết nối được tới backend API. Kiểm tra xem Uvicorn ở cổng 8000 còn chạy không, rồi reload frontend."
          : error instanceof Error
            ? error.message
            : "Đã xảy ra lỗi không xác định.";

      setMessages((current) => [...current, buildErrorMessage(message)]);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className={`app-shell${sidebarOpen ? "" : " app-shell--sidebar-collapsed"}`}>
      <aside className="sidebar-rail">
        <button
          className="rail-button rail-button--active"
          type="button"
          aria-label={sidebarOpen ? "Close sidebar" : "Open sidebar"}
          onClick={() => setSidebarOpen((open) => !open)}
          title={sidebarOpen ? "Close sidebar" : "Open sidebar"}
        >
          {sidebarOpen ? <PanelLeftClose size={18} /> : <PanelLeftOpen size={18} />}
        </button>
        <button className="rail-button" type="button" aria-label="New chat" onClick={handleNewChat} title="New chat">
          <PencilLine size={18} />
        </button>
        <button
          className={`rail-button${searchOpen ? " rail-button--active" : ""}`}
          type="button"
          aria-label="Search sessions"
          title="Search sessions"
          onClick={toggleSearchPanel}
        >
          <Search size={18} />
        </button>
      </aside>

      <aside className={`sidebar${sidebarOpen ? "" : " sidebar--collapsed"}`}>
        <div className="sidebar__brand">
          <span className="sidebar__title">FakeGuard</span>
        </div>

        <div className="sidebar__section">
          <div className="sidebar__label">Chat History</div>
          {searchOpen ? (
            <div className="history-search">
              <input
                type="text"
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                placeholder="Tìm theo claim hoặc câu hỏi..."
              />
            </div>
          ) : null}
          <div className="history-filter-dropdown" ref={historyFilterRef}>
            <button
              type="button"
              className={`history-filter-dropdown__trigger${historyFilterOpen ? " history-filter-dropdown__trigger--open" : ""}`}
              onClick={() => setHistoryFilterOpen((open) => !open)}
              aria-haspopup="menu"
              aria-expanded={historyFilterOpen}
            >
              <span className="history-filter-dropdown__value">
                <span className="history-filter-dropdown__icon">{activeHistoryFilter.icon}</span>
                <span>{activeHistoryFilter.label}</span>
              </span>
              <ChevronDown
                size={16}
                className={`history-filter-dropdown__chevron${historyFilterOpen ? " is-open" : ""}`}
              />
            </button>

            {historyFilterOpen ? (
              <div className="history-filter-dropdown__menu" role="menu">
                {HISTORY_FILTERS.map((filter) => (
                  <button
                    key={filter.value}
                    type="button"
                    className={`history-filter-dropdown__option${historyFilter === filter.value ? " history-filter-dropdown__option--active" : ""}`}
                    onClick={() => {
                      setHistoryFilter(filter.value);
                      setHistoryFilterOpen(false);
                    }}
                    role="menuitemradio"
                    aria-checked={historyFilter === filter.value}
                  >
                    <span className="history-filter-dropdown__icon">{filter.icon}</span>
                    <span>{filter.label}</span>
                  </button>
                ))}
              </div>
            ) : null}
          </div>

          {loadingSessions ? <div className="history-empty">Đang tải lịch sử chat...</div> : null}

          {!loadingSessions && sessions.length === 0 ? <div className="history-empty">Chưa có lịch sử chat.</div> : null}

          {!loadingSessions && sessions.length > 0 ? (
            <div className="history-list">
              {sessions.map((session) => (
                <div
                  key={session.id}
                  className={`history-item${activeSessionId === session.id ? " history-item--active" : ""}`}
                  role="button"
                  tabIndex={0}
                  onClick={() => void loadSession(session.id)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      void loadSession(session.id);
                    }
                  }}
                >
                  <span className="history-item__dot">{sessionSportIcon(session.sport_category)}</span>
                  <span className="history-item__content">
                    <span className="history-item__title">{session.title}</span>
                    <span className="history-item__meta">
                      {sessionSportIcon(session.sport_category)} {sessionSportLabel(session.sport_category)}
                    </span>
                    <span className="history-item__preview">{sessionPreview(session)}</span>
                  </span>
                  <button
                    type="button"
                    className="history-item__delete"
                    aria-label="Xóa session"
                    onClick={(event) => void handleDeleteSession(event, session.id)}
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      </aside>

      <main className="chat-surface">
        <header className="chat-header">
          <div className="chat-header__identity">
            <div className="chat-header__icon">
              <Bot size={18} />
            </div>
            <div>
              <div className="chat-header__title">AI Assistant</div>
              <div className="chat-header__subtitle">Powered by FakeGuard RAG Workflow</div>
            </div>
          </div>
        </header>

        {isEmptyState ? (
          <section className="empty-state">
            <div className="empty-state__hero">
              <div className="empty-state__eyebrow">FakeGuard Fact Check</div>
              <h1 className="empty-state__title">Hôm nay bạn muốn kiểm chứng tin gì?</h1>
              <p className="empty-state__copy">
                Nhập một đoạn tin, tin đồn chuyển nhượng hoặc claim thể thao. Hệ thống sẽ đối chiếu dữ liệu nội bộ và web khi cần.
              </p>
            </div>
            <div className="sport-picker" ref={sportPickerRef}>
              {SPORT_OPTIONS.map((sport) => (
                <button
                  key={sport.value}
                  type="button"
                  className={`sport-picker__chip${selectedSportCategory === sport.value ? " sport-picker__chip--active" : ""}`}
                  onClick={() =>
                    setSelectedSportCategory((current) => (current === sport.value ? null : sport.value))
                  }
                >
                  <span className="sport-picker__icon">{sport.icon}</span>
                  <span>{sport.label}</span>
                </button>
              ))}
            </div>

            <form className="composer composer--hero" onSubmit={handleSubmit}>
              <div className="composer__frame composer__frame--hero">
                <button className="icon-button icon-button--ghost" type="button" aria-label="Attach">
                  <CirclePlus size={18} />
                </button>
                <textarea
                  className="composer__input composer__input--hero"
                  rows={3}
                  placeholder="Nhập đoạn tin thể thao cần kiểm chứng..."
                  value={input}
                  onChange={(event) => setInput(event.target.value)}
                />
                <div className="composer__actions composer__actions--hero">
                  <button className="icon-button icon-button--ghost" type="button" aria-label="Enhance prompt">
                    <Sparkles size={18} />
                  </button>
                  <button className="send-button" type="submit" disabled={!canSubmit}>
                    <SendHorizontal size={18} />
                  </button>
                </div>
              </div>
              <div className="composer__note">Kiểm tra lại các nguồn quan trọng trước khi sử dụng.</div>
            </form>
          </section>
        ) : (
          <>
            <section className="chat-thread">
              <div className="day-pill">Today</div>

              {orderedMessages.map((message) => (
                <MessageBubble key={message.id} message={message} />
              ))}

              {loadingConversation ? (
                <div className="message-row">
                  <div className="assistant-avatar">
                    <LoaderCircle size={16} className="spin" />
                  </div>
                  <div className="message-card message-card--assistant">
                    <div className="message-card__text">Đang tải cuộc trò chuyện...</div>
                  </div>
                </div>
              ) : null}

              {submitting ? (
                <ThinkingProgress
                  elapsedSeconds={thinkingElapsedSeconds}
                  currentStepIndex={thinkingStepIndex}
                  steps={THINKING_STEPS}
                />
              ) : null}

              <div ref={endRef} />
            </section>

            <form className="composer" onSubmit={handleSubmit}>
              <div className="composer__frame">
                <button className="icon-button icon-button--ghost" type="button" aria-label="Attach">
                  <CirclePlus size={18} />
                </button>
                <textarea
                  className="composer__input"
                  rows={1}
                  placeholder="Nhập đoạn tin thể thao cần kiểm chứng..."
                  value={input}
                  onChange={(event) => setInput(event.target.value)}
                />
                <div className="composer__actions">
                  <button className="icon-button icon-button--ghost" type="button" aria-label="Enhance prompt">
                    <Sparkles size={18} />
                  </button>
                  <button className="send-button" type="submit" disabled={!canSubmit}>
                    <SendHorizontal size={18} />
                  </button>
                </div>
              </div>
              <div className="composer__note">Kiểm tra lại các nguồn quan trọng trước khi sử dụng.</div>
            </form>
          </>
        )}
      </main>
    </div>
  );
}

function MessageBubble({ message }) {
  if (message.role === "user") {
    return (
      <div className="message-row message-row--user">
        <div className="message-card message-card--user">
          <div className="message-card__text">{message.content}</div>
          <div className="message-card__meta">{message.timestamp}</div>
        </div>
      </div>
    );
  }

  if (message.type === "result") {
    return <AssistantResponse message={message} />;
  }

  return (
    <div className="message-row">
      <div className="assistant-avatar">
        <Bot size={16} />
      </div>
      <div className="message-stack">
        {message.type === "welcome" ? (
          <div className="message-card message-card--assistant">
            <div className="message-card__text">{message.content}</div>
          </div>
        ) : null}
        {message.type === "error" ? (
          <div className="message-card message-card--error">
            <div className="message-card__text">{message.content}</div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function ThinkingProgress({ elapsedSeconds, currentStepIndex, steps }) {
  return (
    <div className="thinking-progress">
      <div className="thinking-progress__title">Đang kiểm chứng trong {Math.max(1, elapsedSeconds)}s</div>
      <div className="thinking-progress__current">{steps[currentStepIndex]}</div>
      <div className="thinking-progress__list">
        {steps.map((step, index) => (
          <div
            key={step}
            className={`thinking-progress__item${
              index === currentStepIndex ? " thinking-progress__item--active" : index < currentStepIndex ? " thinking-progress__item--done" : ""
            }`}
          >
            <span className="thinking-progress__dot" />
            <span>{step}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function AssistantResponse({ message }) {
  return (
    <div className="assistant-response">
      {message.thinkingDurationSeconds ? (
        <details className="thinking-summary">
          <summary>Tiến trình kiểm chứng {message.thinkingDurationSeconds}s</summary>
          <div className="thinking-summary__body">
            {message.thinkingSteps.map((step) => (
              <div key={step} className="thinking-summary__item">
                <span className="thinking-summary__dot" />
                <span>{step}</span>
              </div>
            ))}
          </div>
        </details>
      ) : null}

      <div className="assistant-response__header">
        <div>
          <div className={`verdict-badge verdict-badge--${verdictTone(message.verdict)}`}>
            {message.verdict ?? "UNKNOWN"}
          </div>
          <div className="assistant-response__summary">{message.summary || "Không có tóm tắt."}</div>
        </div>
        <div className="assistant-response__metrics">
          <Metric label="Confidence" value={formatPercent(message.confidence)} />
          <Metric label="Category" value={formatCategoryLabel(message.category)} />
        </div>
      </div>

      <section className="assistant-section">
        <div className="assistant-section__label">Explanation</div>
        <p className="assistant-section__body">{message.explanation || "Không có giải thích."}</p>
      </section>

      {message.claims.length > 0 ? (
        <section className="assistant-section">
          <div className="assistant-section__label">Sub-claims</div>
          <div className="claim-list">
            {message.claims.map((claim, index) => (
              <div className="claim-item" key={`${claim.claim}-${index}`}>
                <div className="claim-item__head">
                  <span className={`mini-badge mini-badge--${verdictTone(claim.verdict)}`}>
                    {claim.verdict ?? "PENDING"}
                  </span>
                  <span className="claim-item__confidence">{formatPercent(claim.confidence)}</span>
                </div>
                <div className="claim-item__text">{claim.claim}</div>
                {claim.reasoning ? <div className="claim-item__reasoning">{claim.reasoning}</div> : null}
              </div>
            ))}
          </div>
        </section>
      ) : null}

      {message.sources.length > 0 ? (
        <section className="assistant-section">
          <div className="assistant-section__label">Related Sources</div>
          <div className="source-list">
            {message.sources.map((source, index) => (
              <a
                key={`${source.url}-${index}`}
                className="source-item"
                href={source.url}
                target="_blank"
                rel="noreferrer"
              >
                <div className="source-item__title">{source.title || source.url}</div>
                <div className="source-item__url">{source.url}</div>
              </a>
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}

function Metric({ label, value }) {
  return (
    <div className="metric-pill">
      <span className="metric-pill__label">{label}</span>
      <span className="metric-pill__value">{value}</span>
    </div>
  );
}

export default App;
