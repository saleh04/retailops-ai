import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { IconAlert, IconSend } from './icons';

interface ComposerProps {
  onSubmit: (question: string) => void;
  pending: boolean;
  disabled?: boolean;
  error?: string | null;
  placeholder?: string;
}

export function Composer({
  onSubmit,
  pending,
  disabled = false,
  error,
  placeholder = 'Ask a question about your data…',
}: ComposerProps) {
  const [value, setValue] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const submittedRef = useRef(false);

  useEffect(() => {
    const node = textareaRef.current;
    if (!node) return;
    node.style.height = 'auto';
    node.style.height = `${Math.min(node.scrollHeight, 200)}px`;
  }, [value]);

  // Focus returns to the question box once the answer lands — but never on
  // first load, where stealing focus would be unwelcome.
  useEffect(() => {
    if (!submittedRef.current || pending) return;
    submittedRef.current = false;
    textareaRef.current?.focus();
  }, [pending]);

  function send() {
    const question = value.trim();
    if (!question || pending || disabled) return;
    submittedRef.current = true;
    onSubmit(question);
    setValue('');
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      send();
    }
  }

  return (
    <div className="composer">
      {error && (
        <p className="composer__error" role="alert">
          <IconAlert size={14} />
          <span>{error}</span>
        </p>
      )}

      <form
        className="composer__box"
        onSubmit={(event) => {
          event.preventDefault();
          send();
        }}
      >
        <label className="visually-hidden" htmlFor="composer-input">
          Your question
        </label>
        <textarea
          id="composer-input"
          ref={textareaRef}
          className="composer__input"
          rows={1}
          value={value}
          placeholder={placeholder}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={handleKeyDown}
          disabled={pending || disabled}
        />
        <button
          type="submit"
          className="composer__send"
          disabled={pending || disabled || !value.trim()}
          aria-label="Send question"
          title="Send question"
        >
          {pending ? <span className="composer__spinner" aria-hidden="true" /> : <IconSend size={17} />}
        </button>
      </form>

      <p className="composer__hint">
        <kbd>Enter</kbd> to send · <kbd>Shift</kbd>+<kbd>Enter</kbd> for a new line · queries run
        read-only
      </p>
    </div>
  );
}
