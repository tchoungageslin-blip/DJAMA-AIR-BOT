"use client";

import { useEffect, useRef, useState } from "react";
import { Search, Send, User, Bot, UserCheck, AlertTriangle, MessageSquare } from "lucide-react";

interface Session {
  id: string;
  client_id: string;
  phone_number: string;
  first_name: string | null;
  last_name: string | null;
  client_type: string;
  status: string;
  current_intent: string;
  tags: string[];
  ai_summary: string | null;
  updated_at: string;
}

interface Message {
  id: string;
  sender: string;
  content: string;
  created_at: string;
}

export default function InboxPage() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [selectedSession, setSelectedSession] = useState<Session | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [replyText, setReplyText] = useState("");
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<string>("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const selectedSessionRef = useRef<Session | null>(null);

  useEffect(() => {
    fetchSessions();
    const interval = setInterval(fetchSessions, 10000);
    return () => clearInterval(interval);
  }, [filter]);

  // Auto-refresh messages of the selected session every 5s
  useEffect(() => {
    selectedSessionRef.current = selectedSession;
    if (!selectedSession) return;
    const interval = setInterval(async () => {
      const session = selectedSessionRef.current;
      if (!session) return;
      try {
        const res = await fetch(`/api/dashboard/sessions/${session.id}/messages`);
        if (res.ok) {
          const data = await res.json();
          setMessages(data.messages || []);
        }
      } catch {
        // Silent fail
      }
    }, 5000);
    return () => clearInterval(interval);
  }, [selectedSession?.id]);

  // Scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const fetchSessions = async () => {
    try {
      const url = filter
        ? `/api/dashboard/sessions?status=${filter}`
        : "/api/dashboard/sessions";
      const res = await fetch(url);
      if (res.ok) {
        const data = await res.json();
        setSessions(data.sessions || []);
      }
    } catch {
      // Silent fail
    } finally {
      setLoading(false);
    }
  };

  const selectSession = async (session: Session) => {
    setSelectedSession(session);
    try {
      const res = await fetch(`/api/dashboard/sessions/${session.id}/messages`);
      if (res.ok) {
        const data = await res.json();
        setMessages(data.messages || []);
      }
    } catch {
      // Silent fail
    }
  };

  const sendReply = async () => {
    if (!replyText.trim() || !selectedSession) return;

    try {
      await fetch(`/api/dashboard/sessions/${selectedSession.id}/reply`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: replyText }),
      });

      setMessages([
        ...messages,
        {
          id: Date.now().toString(),
          sender: "agent",
          content: replyText,
          created_at: new Date().toISOString(),
        },
      ]);
      setReplyText("");
    } catch {
      // Silent fail
    }
  };

  const takeoverSession = async () => {
    if (!selectedSession) return;
    try {
      await fetch(`/api/dashboard/sessions/${selectedSession.id}/takeover`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ agent_id: "current" }),
      });
      fetchSessions();
      setSelectedSession({ ...selectedSession, status: "HUMAN_ACTIVE" });
    } catch {
      // Silent fail
    }
  };

  const releaseSession = async () => {
    if (!selectedSession) return;
    try {
      await fetch(`/api/dashboard/sessions/${selectedSession.id}/release`, {
        method: "POST",
        headers: { "Content-Type": "application/json" }
      });
      fetchSessions();
      setSelectedSession({ ...selectedSession, status: "BOT_ACTIVE" });
    } catch {
      // Silent fail
    }
  };

  const getStatusBadge = (status: string) => {
    const styles: Record<string, string> = {
      HUMAN_HANDOFF: "bg-orange-100 text-orange-700",
      HUMAN_ACTIVE: "bg-blue-100 text-blue-700",
      BOT_ACTIVE: "bg-green-100 text-green-700",
      RESOLVED: "bg-gray-100 text-gray-700",
    };
    const labels: Record<string, string> = {
      HUMAN_HANDOFF: "Handoff",
      HUMAN_ACTIVE: "Agent",
      BOT_ACTIVE: "Bot",
      RESOLVED: "Résolu",
    };
    return (
      <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${styles[status] || "bg-gray-100"}`}>
        {labels[status] || status}
      </span>
    );
  };

  const getSenderIcon = (sender: string) => {
    if (sender === "bot") return <Bot className="w-4 h-4 text-blue-500" />;
    if (sender === "agent") return <UserCheck className="w-4 h-4 text-green-500" />;
    return <User className="w-4 h-4 text-gray-500" />;
  };

  return (
    <div className="h-[calc(100vh-8rem)] flex flex-col lg:flex-row gap-4">
      {/* Session List */}
      <div className="w-full lg:w-80 flex-shrink-0 bg-white rounded-xl border border-gray-200 flex flex-col overflow-hidden">
        {/* Filters */}
        <div className="p-3 border-b border-gray-100 space-y-2">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              type="text"
              placeholder="Rechercher..."
              className="w-full pl-9 pr-3 py-2 text-sm border border-gray-200 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none"
            />
          </div>
          <div className="flex gap-1 overflow-x-auto">
            {[
              { value: "", label: "Tous" },
              { value: "HUMAN_HANDOFF", label: "Handoff" },
              { value: "HUMAN_ACTIVE", label: "En cours" },
              { value: "BOT_ACTIVE", label: "Bot" },
            ].map((f) => (
              <button
                key={f.value}
                onClick={() => setFilter(f.value)}
                className={`px-3 py-1 rounded-full text-xs font-medium whitespace-nowrap transition ${
                  filter === f.value
                    ? "bg-blue-100 text-blue-700"
                    : "bg-gray-100 text-gray-600 hover:bg-gray-200"
                }`}
              >
                {f.label}
              </button>
            ))}
          </div>
        </div>

        {/* Session items */}
        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="p-4 text-center text-sm text-gray-500">Chargement...</div>
          ) : sessions.length === 0 ? (
            <div className="p-4 text-center text-sm text-gray-500">Aucune conversation</div>
          ) : (
            sessions.map((session) => (
              <button
                key={session.id}
                onClick={() => selectSession(session)}
                className={`w-full p-3 border-b border-gray-50 text-left hover:bg-gray-50 transition ${
                  selectedSession?.id === session.id ? "bg-blue-50" : ""
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="font-medium text-sm text-gray-900 truncate">
                    {session.first_name || session.phone_number}
                  </span>
                  {getStatusBadge(session.status)}
                </div>
                <p className="text-xs text-gray-500 truncate">
                  {session.ai_summary || session.current_intent}
                </p>
                {session.tags?.length > 0 && (
                  <div className="flex gap-1 mt-1 flex-wrap">
                    {session.tags.slice(0, 2).map((tag, i) => (
                      <span key={i} className="text-[10px] px-1.5 py-0.5 bg-yellow-50 text-yellow-700 rounded">
                        {tag}
                      </span>
                    ))}
                  </div>
                )}
              </button>
            ))
          )}
        </div>
      </div>

      {/* Chat Panel */}
      <div className="flex-1 bg-white rounded-xl border border-gray-200 flex flex-col overflow-hidden">
        {selectedSession ? (
          <>
            {/* Chat Header */}
            <div className="p-4 border-b border-gray-100 flex items-center justify-between">
              <div>
                <h3 className="font-semibold text-gray-900">
                  {selectedSession.first_name || selectedSession.phone_number}
                </h3>
                <p className="text-xs text-gray-500">{selectedSession.phone_number}</p>
              </div>
              <div className="flex items-center gap-2">
                {selectedSession.status === "HUMAN_HANDOFF" && (
                  <button
                    onClick={takeoverSession}
                    className="px-3 py-1.5 bg-blue-600 text-white text-xs font-medium rounded-lg hover:bg-blue-700 transition"
                  >
                    Prendre en charge
                  </button>
                )}
                {selectedSession.status === "HUMAN_ACTIVE" && (
                  <button
                    onClick={releaseSession}
                    className="px-3 py-1.5 bg-green-600 text-white text-xs font-medium rounded-lg hover:bg-green-700 transition flex items-center gap-1"
                  >
                    <Bot className="w-3 h-3" />
                    Restituer à l'IA
                  </button>
                )}
                {getStatusBadge(selectedSession.status)}
              </div>
            </div>

            {/* AI Summary Banner */}
            {selectedSession.ai_summary && (
              <div className="mx-4 mt-3 p-3 bg-amber-50 border border-amber-200 rounded-lg">
                <div className="flex items-start gap-2">
                  <AlertTriangle className="w-4 h-4 text-amber-600 mt-0.5" />
                  <div>
                    <p className="text-xs font-medium text-amber-800">Note IA</p>
                    <p className="text-xs text-amber-700 mt-0.5">{selectedSession.ai_summary}</p>
                  </div>
                </div>
              </div>
            )}

            {/* Messages */}
            <div className="flex-1 overflow-y-auto p-4 space-y-3">
              {messages.map((msg) => (
                <div
                  key={msg.id}
                  className={`flex gap-2 ${msg.sender === "client" ? "" : "justify-end"}`}
                >
                  {msg.sender === "client" && (
                    <div className="flex-shrink-0 mt-1">{getSenderIcon(msg.sender)}</div>
                  )}
                  <div
                    className={`max-w-[75%] px-3 py-2 rounded-xl text-sm ${
                      msg.sender === "client"
                        ? "bg-gray-100 text-gray-900"
                        : msg.sender === "bot"
                        ? "bg-blue-50 text-blue-900 border border-blue-100"
                        : "bg-green-50 text-green-900 border border-green-100"
                    }`}
                  >
                    <p className="whitespace-pre-wrap">{msg.content}</p>
                    <p className="text-[10px] text-gray-400 mt-1">
                      {new Date(msg.created_at).toLocaleTimeString("fr-FR", {
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </p>
                  </div>
                  {msg.sender !== "client" && (
                    <div className="flex-shrink-0 mt-1">{getSenderIcon(msg.sender)}</div>
                  )}
                </div>
              ))}
              <div ref={messagesEndRef} />
            </div>

            {/* Reply Input */}
            <div className="p-3 border-t border-gray-100">
              <div className="flex gap-2">
                <input
                  type="text"
                  value={replyText}
                  onChange={(e) => setReplyText(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && sendReply()}
                  placeholder="Taper votre message..."
                  className="flex-1 px-4 py-2.5 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none"
                />
                <button
                  onClick={sendReply}
                  disabled={!replyText.trim()}
                  className="px-4 py-2.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition"
                >
                  <Send className="w-4 h-4" />
                </button>
              </div>
            </div>
          </>
        ) : (
          <div className="flex-1 flex items-center justify-center text-gray-400">
            <div className="text-center">
              <MessageSquare className="w-12 h-12 mx-auto mb-3 opacity-50" />
              <p className="text-sm">Sélectionnez une conversation</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
