"use client";

import { useState, useRef, KeyboardEvent, ChangeEvent } from "react";

interface ChatInputProps {
  onSend: (content: string, attachments?: string[]) => void;
  disabled?: boolean;
  placeholder?: string;
}

export function ChatInput({ onSend, disabled, placeholder }: ChatInputProps) {
  const [input, setInput] = useState("");
  const [attachments, setAttachments] = useState<string[]>([]);
  const [showPreview, setShowPreview] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleSend = () => {
    const trimmed = input.trim();
    if ((!trimmed && attachments.length === 0) || disabled) return;
    onSend(trimmed || "[图片]", attachments.length > 0 ? attachments : undefined);
    setInput("");
    setAttachments([]);
    setShowPreview(false);
    textareaRef.current?.focus();
  };

  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files) return;

    Array.from(files).forEach((file) => {
      if (!file.type.startsWith("image/")) {
        alert("仅支持上传图片文件");
        return;
      }
      if (file.size > 10 * 1024 * 1024) {
        alert("图片大小不能超过 10MB");
        return;
      }
      const reader = new FileReader();
      reader.onload = () => {
        const dataUrl = reader.result as string;
        setAttachments((prev) => [...prev, dataUrl]);
      };
      reader.readAsDataURL(file);
    });

    // Reset input so same file can be re-selected
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const removeAttachment = (index: number) => {
    setAttachments((prev) => prev.filter((_, i) => i !== index));
  };

  return (
    <div
      className={`border-t px-4 py-3 ${
        disabled ? "border-red-800 bg-red-950/20" : "border-slate-800 bg-slate-900/50"
      }`}
    >
      {/* Attachment previews */}
      {attachments.length > 0 && (
        <div className="flex gap-2 mb-3 max-w-3xl mx-auto flex-wrap">
          {attachments.map((dataUrl, i) => (
            <div key={i} className="relative group">
              <img
                src={dataUrl}
                alt={`preview-${i}`}
                className="w-16 h-16 object-cover rounded-lg border border-slate-600"
                onClick={() => setShowPreview(!showPreview)}
              />
              <button
                onClick={() => removeAttachment(i)}
                className="absolute -top-1.5 -right-1.5 w-5 h-5 bg-red-500 text-white rounded-full text-xs flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
              >
                ×
              </button>
              {showPreview && (
                <div
                  className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center"
                  onClick={() => setShowPreview(false)}
                >
                  <img
                    src={dataUrl}
                    alt={`preview-${i}`}
                    className="max-w-[90vw] max-h-[90vh] object-contain rounded-xl"
                  />
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      <div className="flex items-end gap-3 max-w-3xl mx-auto">
        {/* Hidden file input */}
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          multiple
          onChange={handleFileChange}
          className="hidden"
        />

        {/* Attachment button */}
        <button
          onClick={() => fileInputRef.current?.click()}
          className="p-2 text-slate-400 hover:text-white hover:bg-slate-700 rounded-lg transition-colors shrink-0"
          title="上传截图"
          disabled={disabled}
        >
          📎
        </button>

        {/* Input */}
        <textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder || "输入您的 IT 问题..."}
          disabled={disabled}
          rows={1}
          className="flex-1 bg-slate-800 border border-slate-700 rounded-xl px-4 py-2 text-sm
                     text-white placeholder-slate-500 resize-none
                     focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500/50
                     disabled:opacity-50 disabled:cursor-not-allowed"
        />

        {/* Send button */}
        <button
          onClick={handleSend}
          disabled={disabled || (!input.trim() && attachments.length === 0)}
          className={`p-2 rounded-lg transition-colors font-medium text-sm px-4 shrink-0 ${
            disabled || (!input.trim() && attachments.length === 0)
              ? "bg-slate-700 text-slate-500 cursor-not-allowed"
              : "bg-blue-600 text-white hover:bg-blue-500"
          }`}
        >
          发送
        </button>
      </div>
    </div>
  );
}
