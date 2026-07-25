import { useState, useRef, useEffect, type KeyboardEvent } from 'react';
import { createPortal } from 'react-dom';
import { Check, Plus, Tag } from 'lucide-react';
import { TagChip, type TagColorSlot } from '../TagChip';
import './TagPicker.css';

export interface TagOption {
  id: string;
  name: string;
  color_slot: TagColorSlot | null;
}

interface TagPickerProps {
  selectedTagIds: string[];
  tags: TagOption[];
  onChange: (tagIds: string[]) => void;
  onCreateTag?: (name: string) => Promise<TagOption>;
  allowCreate?: boolean;
  triggerLabel?: string;
  ghost?: boolean;
}

interface DropdownPos {
  top: number;
  left: number;
  width: number;
}

export function TagPicker({
  selectedTagIds,
  tags,
  onChange,
  onCreateTag,
  allowCreate = false,
  triggerLabel = 'Add tag',
  ghost = false,
}: TagPickerProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [dropdownPos, setDropdownPos] = useState<DropdownPos | null>(null);
  const [highlightedIndex, setHighlightedIndex] = useState(0);
  const [creating, setCreating] = useState(false);

  const triggerRef = useRef<HTMLButtonElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const filtered = tags.filter((t) =>
    t.name.toLowerCase().includes(query.toLowerCase())
  );

  const showCreate = allowCreate && query.trim() && !filtered.some(
    (t) => t.name.toLowerCase() === query.toLowerCase()
  );

  const totalOptions = filtered.length + (showCreate ? 1 : 0);

  function measureAndOpen() {
    const rect = triggerRef.current?.getBoundingClientRect();
    if (rect) {
      setDropdownPos({
        top: rect.bottom + 2,
        left: rect.left,
        width: Math.max(rect.width, 200),
      });
    }
    setOpen(true);
    setHighlightedIndex(0);
  }

  function close() {
    setOpen(false);
    setQuery('');
  }

  useEffect(() => {
    if (!open) return;
    function handleClick(e: MouseEvent) {
      const t = e.target as Node;
      if (!triggerRef.current?.contains(t) && !listRef.current?.contains(t)) {
        close();
      }
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [open]);

  useEffect(() => {
    if (open && inputRef.current) {
      inputRef.current.focus();
    }
  }, [open]);

  function toggle(id: string) {
    if (selectedTagIds.includes(id)) {
      onChange(selectedTagIds.filter((x) => x !== id));
    } else {
      onChange([...selectedTagIds, id]);
    }
  }

  async function handleCreate() {
    if (!onCreateTag || !query.trim() || creating) return;
    setCreating(true);
    try {
      const newTag = await onCreateTag(query.trim());
      onChange([...selectedTagIds, newTag.id]);
      setQuery('');
    } finally {
      setCreating(false);
    }
  }

  function handleKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (!open) {
      if (e.key === 'ArrowDown' || e.key === 'Enter') measureAndOpen();
      return;
    }
    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        setHighlightedIndex((i) => Math.min(i + 1, totalOptions - 1));
        break;
      case 'ArrowUp':
        e.preventDefault();
        setHighlightedIndex((i) => Math.max(i - 1, 0));
        break;
      case 'Enter':
        e.preventDefault();
        if (highlightedIndex < filtered.length) {
          toggle(filtered[highlightedIndex].id);
        } else if (showCreate) {
          handleCreate();
        }
        break;
      case 'Escape':
        close();
        break;
    }
  }

  const dropdown = open && dropdownPos ? createPortal(
    <div
      ref={listRef}
      className="tag-picker__dropdown"
      style={{
        position: 'fixed',
        top: dropdownPos.top,
        left: dropdownPos.left,
        minWidth: dropdownPos.width,
      }}
    >
      <div className="tag-picker__search">
        <input
          ref={inputRef}
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setHighlightedIndex(0);
          }}
          onKeyDown={handleKeyDown}
          placeholder="Search or create…"
        />
      </div>
      <div className="tag-picker__list">
        {filtered.length === 0 && !showCreate && (
          <div className="tag-picker__empty">No tags found</div>
        )}
        {filtered.map((tag, idx) => {
          const checked = selectedTagIds.includes(tag.id);
          return (
            <div
              key={tag.id}
              className={`tag-picker__option ${idx === highlightedIndex ? 'tag-picker__option--highlighted' : ''}`}
              onMouseDown={(e) => {
                e.preventDefault();
                toggle(tag.id);
              }}
              onMouseEnter={() => setHighlightedIndex(idx)}
            >
              <span className="tag-picker__check">
                {checked && <Check size={14} />}
              </span>
              <TagChip name={tag.name} colorSlot={tag.color_slot} />
            </div>
          );
        })}
        {showCreate && (
          <div
            className={`tag-picker__create ${highlightedIndex === filtered.length ? 'tag-picker__option--highlighted' : ''}`}
            onMouseDown={(e) => {
              e.preventDefault();
              handleCreate();
            }}
            onMouseEnter={() => setHighlightedIndex(filtered.length)}
          >
            <Plus size={14} />
            Create "{query}"
          </div>
        )}
      </div>
    </div>,
    document.body
  ) : null;

  return (
    <div className="tag-picker">
      <button
        ref={triggerRef}
        type="button"
        className={`tag-picker__trigger ${ghost ? 'tag-picker__trigger--ghost' : ''}`}
        onClick={measureAndOpen}
      >
        <Tag size={12} />
        {triggerLabel}
      </button>
      {dropdown}
    </div>
  );
}
