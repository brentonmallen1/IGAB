import { X } from 'lucide-react';
import './TagChip.css';

export type TagColorSlot =
  | 'red'
  | 'orange'
  | 'yellow'
  | 'green'
  | 'teal'
  | 'blue'
  | 'purple'
  | 'pink';

interface TagChipProps {
  name: string;
  colorSlot?: TagColorSlot | null;
  onRemove?: () => void;
  size?: 'sm';
}

export function TagChip({ name, colorSlot, onRemove, size }: TagChipProps) {
  const colorClass = colorSlot ? `tag-chip--${colorSlot}` : 'tag-chip--neutral';
  const sizeClass = size === 'sm' ? 'tag-chip--sm' : '';

  return (
    <span className={`tag-chip ${colorClass} ${sizeClass}`.trim()}>
      {name}
      {onRemove && (
        <button
          type="button"
          className="tag-chip__remove"
          onClick={(e) => {
            e.stopPropagation();
            onRemove();
          }}
          aria-label={`Remove ${name}`}
        >
          <X size={10} />
        </button>
      )}
    </span>
  );
}
